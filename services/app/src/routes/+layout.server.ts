import { PUBLIC_IS_LOCAL, PUBLIC_IS_SPA } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { error, redirect } from '@sveltejs/kit';
import { getPrices } from '$lib/server/nodeCache.js';
import logger from '$lib/logger.js';
import type { OrganizationReadRes, UserRead } from '$lib/types.js';

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const prerender = PUBLIC_IS_SPA !== 'true' ? false : 'auto';
export const ssr = PUBLIC_IS_SPA !== 'true';
export const csr = true;

export const load = async ({ cookies, depends, fetch, locals, params, url }) => {
	depends('layout:root');

	if (params.project_id) {
		cookies.set('activeProjectId', params.project_id, {
			path: '/',
			maxAge: 604800,
			httpOnly: false,
			sameSite: 'strict',
			secure: false
		});
	}

	const prices = await getPrices();

	const showDock = cookies.get('dockOpen');
	const showRightDock = cookies.get('rightDockOpen');

	if (showDock === undefined) {
		cookies.set('dockOpen', 'true', { path: '/', httpOnly: false });
	}
	if (showRightDock === undefined) {
		cookies.set('rightDockOpen', 'false', { path: '/', httpOnly: false });
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

				const userApiRes = await fetch(
					`${JAMAI_URL}/api/admin/backend/v1/users/${locals.user.sub}`,
					{
						headers
					}
				);
				if (userApiRes.status === 404) {
					const userUpsertRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users`, {
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
							userUpsertBody.member_of.length === 0 &&
							!url.pathname.startsWith('/new-organization') &&
							!url.pathname.startsWith('/accept-invite')
						) {
							throw redirect(302, '/new-organization');
						}

						//? Set org ID if not set or if it's not in the list of orgs
						if (
							!activeOrganizationId ||
							!userUpsertBody.member_of.find((org) => org.organization_id === activeOrganizationId)
						) {
							cookies.set('activeOrganizationId', userUpsertBody.member_of[0].organization_id, {
								path: '/',
								sameSite: 'strict',
								maxAge: 604800,
								httpOnly: false,
								secure: false
							});

							activeOrganizationId = cookies.get('activeOrganizationId');
						}

						const orgData = await getOrganizationData(activeOrganizationId!);
						const userRoleInOrg = orgData?.members?.find(
							(user) => user.user_id === locals.user?.sub
						)?.role;

						//* Remove external keys if not admin, don't expose
						if (orgData && userRoleInOrg !== 'admin') {
							delete orgData.external_keys;
							delete orgData.members;

							//* Remove JamAI api keys if not member
							if (userRoleInOrg !== 'member') {
								delete orgData.api_keys;
							}
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
						userApiBody.member_of.length === 0 &&
						!url.pathname.startsWith('/new-organization') &&
						!url.pathname.startsWith('/accept-invite')
					) {
						throw redirect(302, '/new-organization');
					}

					//? Set org ID if not set or if it's not in the list of orgs
					if (
						!activeOrganizationId ||
						!userApiBody.member_of.find((org) => org.organization_id === activeOrganizationId)
					) {
						cookies.set('activeOrganizationId', userApiBody.member_of[0]?.organization_id, {
							path: '/',
							sameSite: 'strict',
							maxAge: 604800,
							httpOnly: false,
							secure: false
						});

						activeOrganizationId = cookies.get('activeOrganizationId');
					}

					const orgData = await getOrganizationData(activeOrganizationId!);
					const userRoleInOrg = orgData?.members?.find(
						(user) => user.user_id === locals.user?.sub
					)?.role;

					//* Remove external keys if not admin, don't expose
					if (orgData && userRoleInOrg !== 'admin') {
						delete orgData.external_keys;
						delete orgData.members;

						//* Remove JamAI api keys if not member
						if (userRoleInOrg !== 'member') {
							delete orgData.api_keys;
						}
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
					logger.error('APP_USER_GET', await userApiRes.json());
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
			activeOrganizationId: 'default',
			dockOpen: cookies.get('dockOpen') == 'true',
			rightDockOpen: cookies.get('rightDockOpen') == 'true'
		};
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	async function getOrganizationData(orgId: string): Promise<OrganizationReadRes | undefined> {
		if (!orgId) return undefined;
		const orgInfoRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/organizations/${orgId}`, {
			headers
		});
		const orgInfoBody = (await orgInfoRes.json()) as OrganizationReadRes;

		if (!orgInfoRes.ok) {
			logger.error('LAYOUTROOT_ORG_GET', orgInfoBody);
		}

		return orgInfoRes.ok ? orgInfoBody : undefined;
	}
};
