import { env } from '$env/dynamic/public';
import { env as privateEnv } from '$env/dynamic/private';
import { dev } from '$app/environment';
import { json, type Handle } from '@sveltejs/kit';
import nodeCache from '$lib/nodeCache';
import logger from '$lib/logger';
import type { OrganizationReadRes, Project } from '$lib/types';

const { PUBLIC_IS_LOCAL } = env;
const { JAMAI_URL, JAMAI_SERVICE_KEY } = privateEnv;

const PROXY_PATHS: { path: string; target: string }[] = [
	{
		path: '/api/v1/gen_tables',
		target: JAMAI_URL
	},
	{
		path: '/api/v1/models',
		target: JAMAI_URL
	},
	{
		path: '/api/v1/model_names',
		target: JAMAI_URL
	},
	{
		path: '/api/v1/chat/completions',
		target: JAMAI_URL
	}
];

const handleApiProxy: Handle = async ({ event }) => {
	const proxyPath = PROXY_PATHS.find((p) => event.url.pathname.startsWith(p.path))!;
	const urlPath = `${proxyPath!.target}${event.url.pathname}${event.url.search}`;
	const proxiedUrl = new URL(urlPath);

	event.request.headers.delete('connection');

	if (PUBLIC_IS_LOCAL === 'false') {
		if (event.locals.user) {
			const projectId =
				event.cookies.get('activeProjectId') || event.request.headers.get('x-project-id');

			if (!projectId) {
				return json({ message: 'Missing project ID' }, { status: 400 });
			}

			//* Get organization ID from project ID
			const projectRes = await fetch(`${JAMAI_URL}/api/admin/v1/projects/${projectId}`, {
				headers: { Authorization: `Bearer ${JAMAI_SERVICE_KEY}` }
			});
			const projectBody = (await projectRes.json()) as Project;

			if (!projectRes.ok) {
				logger.error('APP_PROXY_PROJECTGET', projectBody);
				return json({ message: 'Error fetching project info' }, { status: 500 });
			}

			const orgId = projectBody.organization_id;

			//* Check if user is part of organization
			const orgInfoRes = await fetch(`${JAMAI_URL}/api/admin/v1/organizations/${orgId}`, {
				headers: { Authorization: `Bearer ${JAMAI_SERVICE_KEY}` }
			});
			const orgInfoBody = (await orgInfoRes.json()) as OrganizationReadRes;

			if (!orgInfoRes.ok) {
				logger.error('APP_PROXY_ORGGET', orgInfoBody);
				return json({ message: 'Error fetching organization info' }, { status: 500 });
			}

			if (!orgInfoBody.users!.find((user) => user.user_id === event.locals.user!.sub)) {
				return json({ message: 'Forbidden' }, { status: 403 });
			}

			event.request.headers.append('Authorization', `Bearer ${JAMAI_SERVICE_KEY}`);
			if (!event.request.headers.get('x-project-id')) {
				event.request.headers.append('x-project-id', projectId);
			}
		}
	}

	return fetch(proxiedUrl.toString(), {
		body: event.request.body,
		method: event.request.method,
		headers: event.request.headers,
		//@ts-expect-error missing type
		duplex: 'half'
	}).catch((err) => {
		logger.error('APP_PROXY_ERROR', { url: proxiedUrl.toString(), error: err });
		throw err;
	});
};

export const handle: Handle = async ({ event, resolve }) => {
	if (dev) console.log('Connecting', event.request.url);

	if (PUBLIC_IS_LOCAL === 'false') {
		//? Workaround for event.platform unavailable in development
		if (dev) {
			const user = await (
				await fetch(`${event.url.origin}/dev-profile`, {
					headers: { cookie: `appSession=${event.cookies.get('appSession')}` }
				})
			).json();
			event.locals.user = Object.keys(user).length ? user : undefined;
		} else {
			// @ts-expect-error missing type
			event.locals.user = event.platform?.req?.res?.locals?.user;
		}
	}

	if (PROXY_PATHS.some((p) => event.url.pathname.startsWith(p.path))) {
		return await handleApiProxy({ event, resolve });
	}

	return await resolve(event);
};

//* Server startup script
if (PUBLIC_IS_LOCAL === 'false') {
	(async function () {
		const pricesRes = await fetch(`${JAMAI_URL}/api/admin/v1/prices`, {
			headers: { Authorization: `Bearer ${JAMAI_SERVICE_KEY}` }
		});
		const pricesBody = await pricesRes.json();

		if (!pricesRes.ok) {
			logger.error('APP_PRICES', pricesBody);
			throw new Error('Error fetching prices');
		}

		nodeCache.set('prices', pricesBody);
	})();
}