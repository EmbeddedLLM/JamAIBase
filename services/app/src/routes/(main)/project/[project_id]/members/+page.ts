import { env } from '$env/dynamic/public';
import logger from '$lib/logger';
import type { OrgMemberRead } from '$lib/types';

const { PUBLIC_JAMAI_URL } = env;

export const load = async ({ fetch, parent, data }) => {
	const parentData = await parent();

	const getOrgMembers = async () => {
		const activeOrganizationId = parentData.organizationData?.id;
		if (!activeOrganizationId) {
			return { error: 400, message: 'No active organization' };
		}

		const orgMembersRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/organizations/members/list?${new URLSearchParams([['organization_id', activeOrganizationId]])}`
		);
		const orgMembersBody = await orgMembersRes.json();

		if (!orgMembersRes.ok) {
			logger.error('PROJTEAM_ORGMEMBERS_ERROR', orgMembersBody);
			return { error: orgMembersRes.status, message: orgMembersBody };
		} else {
			return {
				data: orgMembersBody.items as OrgMemberRead[]
			};
		}
	};

	return {
		...data,
		organizationMembers: await getOrgMembers()
	};
};
