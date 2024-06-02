import { env } from '$env/dynamic/public';
import { env as privateEnv } from '$env/dynamic/private';
import { error, redirect } from '@sveltejs/kit';
import nodeCache from '$lib/nodeCache.js';
import logger from '$lib/logger.js';
import type { OrganizationReadRes, PriceRes, UserRead } from '$lib/types.js';

const { PUBLIC_IS_LOCAL } = env;
const { JAMAI_URL, JAMAI_SERVICE_KEY } = privateEnv;

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const load = async ({ cookies, depends, fetch, locals, params, url }) => {
	depends('layout:root');

	if (params.project_id) {
		cookies.set('activeProjectId', params.project_id, {
			path: '/',
			maxAge: 3153600,
			httpOnly: false,
			sameSite: 'strict'
		});
	}

	const prices = nodeCache.get('prices') as PriceRes;

	const showDock = cookies.get('dockOpen');
	const showRightDock = cookies.get('rightDockOpen');

	if (showDock === undefined) {
		cookies.set('dockOpen', 'true', { path: '/', httpOnly: false });
	}
	if (showRightDock === undefined) {
		cookies.set('rightDockOpen', 'true', { path: '/', httpOnly: false });
	}

	if (PUBLIC_IS_LOCAL === 'false' && !url.pathname.startsWith('/api')) {
		if (!locals.user) {
			const originalUrl =
				url.pathname + (url.searchParams.size > 0 ? `?${url.searchParams.toString()}` : '');
			throw redirect(302, `/login${originalUrl ? `?returnTo=${originalUrl}` : ''}`);
		} else {
			if (!locals.user.email_verified && !url.pathname.startsWith('/verify-email')) {
				throw redirect(
					302,
					`/verify-email${url.searchParams.size > 0 ? `?${url.searchParams.toString()}` : ''}`
				);
			}

			if (locals.user.email_verified) {
				let activeOrganizationId = cookies.get('activeOrganizationId');

				const userApiRes = await fetch(`${JAMAI_URL}/api/admin/v1/users/${locals.user.sub}`, {
					headers
				});
				if (userApiRes.status === 404) {
					const userUpsertRes = await fetch(`${JAMAI_URL}/api/admin/v1/users`, {
						method: 'POST',
						headers: {
							...headers,
							'Content-Type': 'application/json'
						},
						body: JSON.stringify({
							id: locals.user.sub,
							name:
								locals.user.email === locals.user.name ? locals.user.nickname : locals.user.name,
							description: '',
							email: locals.user.email
						})
					});
					const userUpsertBody = (await userUpsertRes.json()) as UserRead;

					if (userUpsertRes.ok) {
						//? Redirect to create org if no orgs
						if (
							userUpsertBody.organizations.length === 0 &&
							!url.pathname.startsWith('/new-organization') &&
							!url.pathname.startsWith('/accept-invite')
						) {
							throw redirect(302, '/new-organization');
						}

						//? Set org ID if not set or if it's not in the list of orgs
						if (
							!activeOrganizationId ||
							!userUpsertBody.organizations.find(
								(org) => org.organization_id === activeOrganizationId
							)
						) {
							cookies.set('activeOrganizationId', userUpsertBody.organizations[0].organization_id, {
								path: '/',
								sameSite: 'strict',
								maxAge: 3153600000,
								httpOnly: false
							});

							activeOrganizationId = cookies.get('activeOrganizationId');
						}

						const orgData = await getOrganizationData(activeOrganizationId!);

						//* Remove external keys if not admin, don't expose
						if (
							orgData &&
							orgData.users!.find((user) => user.user_id === locals.user?.sub)?.role !== 'admin'
						) {
							delete orgData.external_keys;
							delete orgData.api_keys;
							delete orgData.users;
						}

						return {
							prices,
							user: locals.user,
							userData: userUpsertBody,
							dockOpen: cookies.get('dockOpen') == 'true',
							rightDockOpen: cookies.get('rightDockOpen') == 'true',
							activeOrganizationId,
							organizationData: orgData
						};
					} else {
						logger.error('APP_USER_UPSERT', userUpsertBody);
						// eslint-disable-next-line @typescript-eslint/no-explicit-any
						throw error(userUpsertRes.status, userUpsertBody as any);
					}
				} else if (userApiRes.ok) {
					const userApiBody = (await userApiRes.json()) as UserRead;

					//? Redirect to create org if no orgs
					if (
						userApiBody.organizations.length === 0 &&
						!url.pathname.startsWith('/new-organization') &&
						!url.pathname.startsWith('/accept-invite')
					) {
						throw redirect(302, '/new-organization');
					}

					//? Set org ID if not set or if it's not in the list of orgs
					if (
						!activeOrganizationId ||
						!userApiBody.organizations.find((org) => org.organization_id === activeOrganizationId)
					) {
						cookies.set('activeOrganizationId', userApiBody.organizations[0]?.organization_id, {
							path: '/',
							sameSite: 'strict',
							maxAge: 3153600000,
							httpOnly: false
						});

						activeOrganizationId = cookies.get('activeOrganizationId');
					}

					const orgData = await getOrganizationData(activeOrganizationId!);

					//* Remove external keys if not admin, don't expose
					if (
						orgData &&
						orgData.users!.find((user) => user.user_id === locals.user?.sub)?.role !== 'admin'
					) {
						delete orgData.external_keys;
						delete orgData.api_keys;
						delete orgData.users;
					}

					return {
						prices,
						user: locals.user,
						userData: userApiBody,
						dockOpen: cookies.get('dockOpen') == 'true',
						rightDockOpen: cookies.get('rightDockOpen') == 'true',
						activeOrganizationId,
						organizationData: orgData
					};
				} else {
					//FIXME: Throw error if user API fails, maybe?
					return {
						prices,
						user: locals.user,
						dockOpen: cookies.get('dockOpen') == 'true',
						rightDockOpen: cookies.get('rightDockOpen') == 'true'
					};
					throw error(userApiRes.status, await userApiRes.json());
				}
			} else {
				return {
					prices,
					user: locals.user,
					dockOpen: cookies.get('dockOpen') == 'true',
					rightDockOpen: cookies.get('rightDockOpen') == 'true'
				};
			}
		}
	} else {
		return {
			prices,
			user: locals.user,
			dockOpen: cookies.get('dockOpen') == 'true',
			rightDockOpen: cookies.get('rightDockOpen') == 'true'
		};
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	async function getOrganizationData(orgId: string): Promise<OrganizationReadRes | undefined> {
		if (!orgId) return undefined;
		const orgInfoRes = await fetch(`${JAMAI_URL}/api/admin/v1/organizations/${orgId}`, { headers });
		const orgInfoBody = (await orgInfoRes.json()) as OrganizationReadRes;

		if (!orgInfoRes.ok) {
			logger.error('LAYOUTROOT_ORG_GET', orgInfoBody);
		}

		return orgInfoRes.ok ? orgInfoBody : undefined;
	}
};
