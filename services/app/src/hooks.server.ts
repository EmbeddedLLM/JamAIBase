import { dev } from '$app/environment';
import { env } from '$env/dynamic/private';
import { handle as authenticationHandle } from '$lib/auth';
import logger from '$lib/logger';
import { paraglideMiddleware } from '$lib/paraglide/server';
import { getPrices } from '$lib/server/nodeCache';
import type { Auth0User, User } from '$lib/types';
import { error, redirect, type Handle } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { Agent } from 'undici';

const { AUTH0_CLIENT_SECRET, OWL_SERVICE_KEY, OWL_URL } = env;
const ossMode = !OWL_SERVICE_KEY;
const auth0Mode = !!OWL_SERVICE_KEY && !!AUTH0_CLIENT_SECRET;

const PROXY_PATHS: { path: string; exclude?: string[]; target: string }[] = [
	{
		path: '/api/owl/organizations',
		exclude: ['/api/owl/organizations/webhooks/stripe'],
		target: `${OWL_URL}/api/v2/organizations`
	},
	{
		path: '/api/owl/projects',
		// exclude: ['/api/owl/projects/export', '/api/owl/projects/import'],
		target: `${OWL_URL}/api/v2/projects`
	},
	{
		path: '/api/owl/gen_tables',
		target: `${OWL_URL}/api/v2/gen_tables`
	},
	{
		path: '/api/owl/models',
		target: `${OWL_URL}/api/v2/models`
	},
	{
		path: '/api/owl/model_names',
		target: `${OWL_URL}/api/v2/model_names`
	},
	{
		path: '/api/owl/chat/completions',
		target: `${OWL_URL}/api/v2/chat/completions`
	},
	{
		path: '/api/owl/conversations',
		target: `${OWL_URL}/api/v2/conversations`
	},
	{
		path: '/api/owl/files',
		target: `${OWL_URL}/api/v2/files`
	},
	{
		path: '/api/file',
		target: `${OWL_URL}/api/v2/file`
	},
	{
		path: '/api/owl/templates',
		target: `${OWL_URL}/api/v2/templates`
	}
];

const handleApiProxy: Handle = async ({ event }) => {
	const proxyPath = PROXY_PATHS.find((p) => event.url.pathname.startsWith(p.path))!;
	const urlPath = `${proxyPath.target}${event.url.pathname.replace(proxyPath.path, '')}${event.url.search}`;
	const proxiedUrl = new URL(urlPath);

	event.request.headers.delete('connection');

	if (event.locals.user || ossMode) {
		event.request.headers.append('Authorization', `Bearer ${OWL_SERVICE_KEY}`);
		event.request.headers.append('x-user-id', event.locals.user?.id ?? '0');
	}

	if (!event.request.headers.get('x-project-id') && event.cookies.get('activeProjectId')) {
		event.request.headers.append('x-project-id', event.cookies.get('activeProjectId')!);
	}

	// const projectId =
	// 	event.request.headers.get('x-project-id') || event.cookies.get('activeProjectId');
	// if (!projectId) {
	// 	return json({ message: 'Missing project ID' }, { status: 400 });
	// }

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

export const mainHandle: Handle = async ({ event, resolve }) => {
	const { cookies, locals, request, url } = event;
	if (dev && !request.url.includes('/api/owl/files')) console.log('Connecting', request.url);

	locals.ossMode = ossMode;
	locals.auth0Mode = auth0Mode;

	let auth0UserData: Auth0User;
	if (auth0Mode) {
		//? Workaround for event.platform unavailable in development
		if (dev) {
			const user = await (
				await fetch(`${url.origin}/dev-profile`, {
					headers: { cookie: `appSession=${cookies.get('appSession')}` }
				})
			).json();
			auth0UserData = Object.keys(user).length ? user : undefined;
		} else {
			// @ts-expect-error missing type
			auth0UserData = event.platform?.req?.res?.locals?.user;
		}
	}

	const session = !auth0Mode && !ossMode ? await event.locals.auth?.() : null;
	const sessionUserId = session?.user?.id;

	//@ts-expect-error asd
	if (auth0UserData || ossMode || sessionUserId) {
		//@ts-expect-error asd
		let userApiData = await getUserApiData(auth0UserData?.sub ?? sessionUserId ?? '0');
		if (!userApiData.data) {
			if (auth0Mode && userApiData.status === 404) {
				const userUpsertRes = await fetch(`${OWL_URL}/api/v2/users`, {
					method: 'POST',
					headers: {
						Authorization: `Bearer ${OWL_SERVICE_KEY}`,
						'Content-Type': 'application/json'
					},
					body: JSON.stringify({
						id: auth0UserData!.sub,
						name:
							auth0UserData!.email === auth0UserData!.name
								? auth0UserData!.nickname
								: auth0UserData!.name,
						email: auth0UserData!.email,
						email_verified: true
					})
				});
				const userUpsertBody = (await userUpsertRes.json()) as User;

				if (!userUpsertRes.ok) {
					logger.error('APP_USER_UPSERT', userUpsertBody);
					// eslint-disable-next-line @typescript-eslint/no-explicit-any
					throw error(userUpsertRes.status, userUpsertBody as any);
				} else {
					userApiData = { status: 200, data: userUpsertBody };
				}
			} else {
				// logger.error('APP_USER_GET', `User not found: ${session.user.id}`);
				if (!url.pathname.startsWith('/login') && !url.pathname.startsWith('/register')) {
					throw redirect(302, '/login');
				}
			}
		}
		locals.user = {
			...(auth0UserData! ?? {}),
			...userApiData.data!,
			email_verified: (auth0UserData! ?? {}).email_verified ?? userApiData.data!.email_verified
		};
	}

	//? Bandaid fix for email verification - REMOVE LATER
	/* if (auth0Mode && locals.user) {
		await fetch(
			`${OWL_URL}/api/v2/users/verify/email/code?${new URLSearchParams([
				['user_email', locals.user.email],
				['valid_days', '7']
			])}`,
			{
				method: 'POST',
				headers: { Authorization: `Bearer ${OWL_SERVICE_KEY}`, 'x-user-id': locals.user.sub! }
			}
		)
			.then((r) => r.json())
			.then((emailCode) =>
				fetch(
					`${OWL_URL}/api/v2/users/verify/email?${new URLSearchParams([['verification_code', emailCode.id]])}`,
					{
						method: 'POST',
						headers: { Authorization: `Bearer ${OWL_SERVICE_KEY}`, 'x-user-id': locals.user!.sub! }
					}
				)
			);
	} */

	if (
		!ossMode &&
		!url.pathname.startsWith('/api') &&
		!url.pathname.startsWith('/login') &&
		!url.pathname.startsWith('/register')
	) {
		if (!locals.user) {
			const originalUrl =
				url.pathname + (url.searchParams.size > 0 ? `?${url.searchParams.toString()}` : '');
			throw redirect(
				302,
				`/login${originalUrl ? `?returnTo=${encodeURIComponent(originalUrl)}` : ''}`
			);
		}
	}

	if (
		PROXY_PATHS.some(
			(p) =>
				url.pathname.startsWith(p.path) &&
				(!p.exclude || !p.exclude.some((ex) => url.pathname.startsWith(ex)))
		)
	) {
		return await handleApiProxy({ event, resolve });
	}

	return await resolve(event);
};

const paraglideHandle: Handle = ({ event, resolve }) =>
	paraglideMiddleware(event.request, ({ request: localizedRequest, locale }) => {
		event.request = localizedRequest;
		return resolve(event, {
			transformPageChunk: ({ html }) => {
				return html.replace('%lang%', locale);
			}
		});
	});

export const handle: Handle = sequence(authenticationHandle, mainHandle, paraglideHandle);

//* Server startup script
(async function () {
	await getPrices();
})();

async function getUserApiData(userId: string) {
	const userApiRes = await fetch(
		`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', userId]])}`,
		{
			headers: {
				Authorization: `Bearer ${OWL_SERVICE_KEY}`,
				'x-user-id': userId
			}
		}
	);

	const userApiBody = await userApiRes.json();
	if (userApiRes.ok) {
		return { status: 200, data: userApiBody as User };
	} else {
		if (!/User "([^"]*)" is not found\./.test(userApiBody.message)) {
			logger.error('APP_USER_GET', userApiBody);
			return { status: userApiRes.status, data: undefined };
		} else {
			return { status: 404, data: undefined };
		}
	}
}
