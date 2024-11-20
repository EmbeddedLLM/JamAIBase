import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { dev } from '$app/environment';
import { json, type Handle } from '@sveltejs/kit';
import { Agent } from 'undici';
import { getPrices } from '$lib/server/nodeCache';
import logger from '$lib/logger';

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
	},
	{
		path: '/api/v1/files',
		target: JAMAI_URL
	},
	{
		path: '/api/file',
		target: JAMAI_URL
	},
	{
		path: '/api/public/v1/templates',
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
			event.request.headers.append('Authorization', `Bearer ${JAMAI_SERVICE_KEY}`);
			event.request.headers.append('x-user-id', event.locals.user.sub);
		}
	}

	const projectId =
		event.request.headers.get('x-project-id') || event.cookies.get('activeProjectId');
	if (!projectId) {
		return json({ message: 'Missing project ID' }, { status: 400 });
	}

	if (!event.request.headers.get('x-project-id')) {
		event.request.headers.append('x-project-id', projectId);
	}

	return fetch(proxiedUrl.toString(), {
		body: event.request.body,
		method: event.request.method,
		headers: event.request.headers,
		//@ts-expect-error missing type
		duplex: 'half',
		dispatcher: new Agent({
			connectTimeout: 0,
			headersTimeout: 0,
			bodyTimeout: 0
		})
	}).catch((err) => {
		if (err.cause.message !== 'aborted') {
			logger.error('APP_PROXY_ERROR', { url: proxiedUrl.toString(), error: err });
			throw err;
		}
		return new Response('Internal Server Error', { status: 500 });
	});
};

export const handle: Handle = async ({ event, resolve }) => {
	if (dev && !event.request.url.includes('/api/v1/files'))
		console.log('Connecting', event.request.url);

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
		await getPrices();
	})();
}
