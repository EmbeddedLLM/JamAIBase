import { PUBLIC_ADMIN_ORGANIZATION_ID } from '$env/static/public';
import { error, redirect } from '@sveltejs/kit';

export async function load({ cookies, locals }) {
	if (
		cookies.get('activeOrganizationId') !== PUBLIC_ADMIN_ORGANIZATION_ID ||
		!locals.user?.org_memberships.find(
			(org) => org.organization_id === PUBLIC_ADMIN_ORGANIZATION_ID
		)
	) {
		throw error(404, 'Not found');
	}

	throw redirect(302, '/system/models');
}
