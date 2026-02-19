import { env } from '$env/dynamic/private';
import { PUBLIC_IS_SPA } from '$env/static/public';
import logger from '$lib/logger.js';
import type { OrganizationReadRes } from '$lib/types.js';
import { redirect } from '@sveltejs/kit';
import type { LayoutServerLoadEvent } from './$types.js';

interface Data {
	user: App.Locals['user'];
	dockOpen: boolean;
	rightDockOpen: boolean;
	activeOrganizationId?: string;
	organizationData?: OrganizationReadRes;
	OWL_STRIPE_PUBLISHABLE_KEY: string;
}

const {
	OWL_SERVICE_KEY,
	OWL_URL,
	OWL_STRIPE_PUBLISHABLE_KEY_LIVE,
	OWL_STRIPE_PUBLISHABLE_KEY_TEST
} = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const prerender = PUBLIC_IS_SPA !== 'true' ? false : 'auto';
export const ssr = PUBLIC_IS_SPA !== 'true';
export const csr = true;

export const load: (event: LayoutServerLoadEvent) => Promise<Data> = async ({
	cookies,
	depends,
	fetch,
	locals,
	params,
	url
}) => {
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

	const showDock = cookies.get('dockOpen') === 'true';
	const showRightDock = cookies.get('rightDockOpen') === 'true';

	if (showDock === undefined) {
		cookies.set('dockOpen', 'true', { path: '/', httpOnly: false });
	}
	if (showRightDock === undefined) {
		cookies.set('rightDockOpen', 'false', { path: '/', httpOnly: false });
	}

	if (!url.pathname.startsWith('/login') && !url.pathname.startsWith('/register')) {
		if (
			!locals.ossMode &&
			locals.checkEmailVerification &&
			!locals.user!.email_verified &&
			!url.pathname.startsWith('/verify-email')
		) {
			throw redirect(
				302,
				`/verify-email${url.searchParams.size > 0 ? `?${url.searchParams}` : ''}`
			);
		}

		if (locals.ossMode || locals.user?.email_verified || !locals.checkEmailVerification) {
			let activeOrganizationId = cookies.get('activeOrganizationId');

			//? Redirect to create org if no orgs
			if (
				locals.user?.org_memberships.length === 0 &&
				!url.pathname.startsWith('/new-organization') &&
				!url.pathname.startsWith('/join-organization')
			) {
				throw redirect(302, '/new-organization');
			}

			//? Set org ID if not set or if it's not in the list of orgs
			if (
				locals.user?.org_memberships.length !== 0 &&
				(!activeOrganizationId ||
					!locals.user?.org_memberships.find((org) => org.organization_id === activeOrganizationId))
			) {
				cookies.set('activeOrganizationId', locals.user!.org_memberships[0].organization_id!, {
					path: '/',
					sameSite: 'strict',
					maxAge: 604800,
					httpOnly: false,
					secure: false
				});

				activeOrganizationId = cookies.get('activeOrganizationId');
			}

			const orgData = await getOrganizationData(activeOrganizationId!);
			const userRoleInOrg = locals.user?.org_memberships.find(
				(org) => org.organization_id === activeOrganizationId
			)?.role;

			//* Obfuscate external keys if not admin
			if (orgData && userRoleInOrg !== 'ADMIN') {
				if (orgData.external_keys) {
					orgData.external_keys = Object.fromEntries(
						Object.entries(orgData.external_keys).map(([key, value]) => [
							key,
							value.trim() === '' ? '' : '********'
						])
					);
				}

				//* Obfuscate credit
				orgData.credit = orgData.credit > 0 ? 1 : 0;
				orgData.credit_grant = orgData.credit_grant > 0 ? 1 : 0;
			}

			return {
				user: locals.user,
				dockOpen: cookies.get('dockOpen') === 'true',
				rightDockOpen: cookies.get('rightDockOpen') === 'true',
				activeOrganizationId,
				organizationData: orgData,
				ossMode: locals.ossMode,
				auth0Mode: locals.auth0Mode,
				OWL_STRIPE_PUBLISHABLE_KEY:
					OWL_STRIPE_PUBLISHABLE_KEY_LIVE || OWL_STRIPE_PUBLISHABLE_KEY_TEST || ''
			};
		} else {
			return {
				user: locals.user,
				dockOpen: cookies.get('rightDockOpen') === 'true',
				rightDockOpen: cookies.get('rightDockOpen') === 'true',
				ossMode: locals.ossMode,
				auth0Mode: locals.auth0Mode,
				OWL_STRIPE_PUBLISHABLE_KEY:
					OWL_STRIPE_PUBLISHABLE_KEY_LIVE || OWL_STRIPE_PUBLISHABLE_KEY_TEST || ''
			};
		}
	} else {
		return {
			user: locals.user,
			activeOrganizationId: 'default',
			dockOpen: cookies.get('rightDockOpen') === 'true',
			rightDockOpen: cookies.get('rightDockOpen') === 'true',
			ossMode: locals.ossMode,
			auth0Mode: locals.auth0Mode,
			OWL_STRIPE_PUBLISHABLE_KEY:
				OWL_STRIPE_PUBLISHABLE_KEY_LIVE || OWL_STRIPE_PUBLISHABLE_KEY_TEST || ''
		};
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	async function getOrganizationData(orgId: string): Promise<OrganizationReadRes | undefined> {
		if (!orgId) return undefined;
		const orgInfoRes = await fetch(
			`${OWL_URL}/api/v2/organizations?${new URLSearchParams([['organization_id', orgId]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? ''
				}
			}
		);
		const orgInfoBody = (await orgInfoRes.json()) as OrganizationReadRes;

		if (!orgInfoRes.ok) {
			logger.error('LAYOUTROOT_ORG_GET', orgInfoBody);
		}

		return orgInfoRes.ok ? orgInfoBody : undefined;
	}
};
