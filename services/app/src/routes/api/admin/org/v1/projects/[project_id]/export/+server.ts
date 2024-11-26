import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { json } from '@sveltejs/kit';
import logger, { APIError } from '$lib/logger.js';
import type { UserRead } from '$lib/types.js';

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const GET = async ({ locals, params }) => {
	const projectId = params.project_id;

	if (PUBLIC_IS_LOCAL === 'false') {
		//* Verify user perms
		if (!locals.user) {
			return json(new APIError('Unauthorized'), { status: 401 });
		}

		const projectApiRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects/${projectId}`, {
			headers
		});
		const projectApiBody = await projectApiRes.json();

		if (!projectApiRes.ok) {
			logger.error('PROJECT_EXPORT_GETPROJ', projectApiBody);
		}

		const userApiRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users/${locals.user.sub}`, {
			headers
		});
		const userApiBody = (await userApiRes.json()) as UserRead;

		if (userApiRes.ok) {
			const targetOrg = userApiBody.member_of.find(
				(org) => org.organization_id === projectApiBody.organization_id
			);
			if (!targetOrg) {
				return json(new APIError('Forbidden'), { status: 403 });
			}
		} else {
			logger.error('PROJECT_EXPORT_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	const exportProjectRes = await fetch(
		`${JAMAI_URL}/api/admin/org/v1/projects/${projectId}/export`,
		{
			headers
		}
	);

	if (!exportProjectRes.ok) {
		const exportProjectBody = await exportProjectRes.json();
		logger.error('PROJECT_EXPORT_EXPORT', exportProjectBody);
		return json(new APIError('Failed to export project', exportProjectBody as any), {
			status: exportProjectRes.status
		});
	} else {
		return exportProjectRes;
	}
};
