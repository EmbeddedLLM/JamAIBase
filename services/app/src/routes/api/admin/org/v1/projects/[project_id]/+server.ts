import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { json } from '@sveltejs/kit';
import logger, { APIError } from '$lib/logger.js';
import type { Project, UserRead } from '$lib/types.js';

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const GET = async ({ locals, params }) => {
	if (PUBLIC_IS_LOCAL === 'false') {
		if (!locals.user) {
			return json(new APIError('Unauthorized'), { status: 401 });
		}
	}

	const projectRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects/${params.project_id}`, {
		headers
	});
	const projectBody = await projectRes.json();

	if (projectRes.ok) {
		if (
			PUBLIC_IS_LOCAL !== 'false' ||
			(projectBody as Project).organization.members?.find(
				(user) => user.user_id === locals.user?.sub
			)
		) {
			return json(projectBody);
		} else {
			return json(new APIError('Project not found'), { status: 404 });
		}
	} else {
		return json(new APIError('Failed to get project', projectBody as any), {
			status: projectRes.status
		});
	}
};

export const DELETE = async ({ locals, params }) => {
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
			logger.error('PROJECT_DELETE_GETPROJ', projectApiBody);
		}

		const userApiRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users/${locals.user.sub}`, {
			headers
		});
		const userApiBody = (await userApiRes.json()) as UserRead;

		if (userApiRes.ok) {
			const targetOrg = userApiBody.member_of.find(
				(org) => org.organization_id === projectApiBody.organization_id
			);
			if (!targetOrg || targetOrg.role !== 'admin') {
				return json(new APIError('Forbidden'), { status: 403 });
			}
		} else {
			logger.error('PROJECT_DELETE_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	const deleteProjectRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects/${projectId}`, {
		method: 'DELETE',
		headers
	});

	const deleteProjectBody = await deleteProjectRes.json();
	if (!deleteProjectRes.ok) {
		logger.error('PROJECT_DELETE_DELETE', deleteProjectBody);
		return json(new APIError('Failed to delete project', deleteProjectBody as any), {
			status: deleteProjectRes.status
		});
	} else {
		return json({ ok: true });
	}
};
