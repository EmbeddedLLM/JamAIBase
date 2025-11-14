import { env } from '$env/dynamic/private';
import logger, { APIError } from '$lib/logger.js';
import type { User } from '$lib/types.js';
import { fail } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const actions = {
	update: async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const organization_name = data.get('organization_name');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof organization_name !== 'string' || organization_name.trim() === '') {
			return fail(400, new APIError('Invalid organization name').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const userApiRes = await fetch(
			`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', locals.user.id]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);
		const userApiBody = (await userApiRes.json()) as User;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.org_memberships.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg || targetOrg.role !== 'ADMIN') {
				return fail(403, new APIError('Forbidden').getSerializable());
			}
		} else {
			logger.error('ORG_UPDATE_USERGET', userApiBody);
			return fail(
				userApiRes.status,
				new APIError('Failed to get user', userApiBody as any).getSerializable()
			);
		}

		const updateOrgRes = await fetch(
			`${OWL_URL}/api/v2/organizations?${new URLSearchParams([['organization_id', activeOrganizationId]])}`,
			{
				method: 'PATCH',
				headers: {
					...headers,
					'x-user-id': locals.user.id,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					name: organization_name
				})
			}
		);

		const updateOrgBody = await updateOrgRes.json();
		if (!updateOrgRes.ok) {
			logger.error('ORG_UPDATE_UPDATE', updateOrgBody);
			return fail(
				updateOrgRes.status,
				new APIError('Failed to update organization', updateOrgBody as any).getSerializable()
			);
		} else {
			return updateOrgBody;
		}
	},

	leave: async ({ cookies, fetch, locals }) => {
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const userApiRes = await fetch(
			`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', locals.user.id]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);
		const userApiBody = (await userApiRes.json()) as User;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.org_memberships.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg) {
				return fail(403, new APIError('Forbidden').getSerializable());
			}
		} else {
			logger.error('ORG_LEAVE_USERGET', userApiBody);
			return fail(
				userApiRes.status,
				new APIError('Failed to get user', userApiBody as any).getSerializable()
			);
		}

		const leaveOrgRes = await fetch(
			`${OWL_URL}/api/v2/organizations/members?${new URLSearchParams([
				['user_id', locals.user.id],
				['organization_id', activeOrganizationId]
			])}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);

		const leaveOrgBody = await leaveOrgRes.json();
		if (!leaveOrgRes.ok) {
			logger.error('ORG_LEAVE_DELETE', leaveOrgBody);
			return fail(
				leaveOrgRes.status,
				new APIError('Failed to leave organization', leaveOrgBody as any).getSerializable()
			);
		} else {
			return leaveOrgBody;
		}
	},

	delete: async ({ cookies, fetch, locals }) => {
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const userApiRes = await fetch(
			`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', locals.user.id]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);
		const userApiBody = (await userApiRes.json()) as User;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.org_memberships.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg || targetOrg.role !== 'ADMIN') {
				return fail(403, new APIError('Forbidden').getSerializable());
			}
		} else {
			logger.error('ORG_DELETE_USERGET', userApiBody);
			return fail(
				userApiRes.status,
				new APIError('Failed to get user', userApiBody as any).getSerializable()
			);
		}

		const deleteOrgRes = await fetch(
			`${OWL_URL}/api/v2/organizations?${new URLSearchParams([['organization_id', activeOrganizationId]])}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);

		const deleteOrgBody = await deleteOrgRes.json();
		if (!deleteOrgRes.ok) {
			logger.error('ORG_DELETE_DELETE', deleteOrgBody);
			return fail(
				deleteOrgRes.status,
				new APIError('Failed to delete organization', deleteOrgBody as any).getSerializable()
			);
		} else {
			return deleteOrgBody;
		}
	}
};
