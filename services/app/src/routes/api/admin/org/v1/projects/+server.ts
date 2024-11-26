import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { json } from '@sveltejs/kit';
import { projectIDPattern } from '$lib/constants.js';
import logger, { APIError } from '$lib/logger.js';
import type { UserRead } from '$lib/types.js';

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const GET = async ({ cookies, locals, url }) => {
	const activeOrganizationId = cookies.get('activeOrganizationId');

	if (PUBLIC_IS_LOCAL === 'false') {
		if (!activeOrganizationId) {
			return json(new APIError('No active organization'), { status: 400 });
		}

		//* Verify user perms
		if (!locals.user) {
			return json(new APIError('Unauthorized'), { status: 401 });
		}

		const userApiRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users/${locals.user.sub}`, {
			headers
		});
		const userApiBody = (await userApiRes.json()) as UserRead;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.member_of.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg) {
				return json(new APIError('Forbidden'), { status: 403 });
			}
		} else {
			logger.error('PROJECT_LIST_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	const searchParams = new URLSearchParams({ organization_id: activeOrganizationId ?? '' });
	url.searchParams.forEach((value, key) => {
		if (key === 'organization_id' && PUBLIC_IS_LOCAL === 'false') return;
		searchParams.set(key, value);
	});

	const projectsListRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects?${searchParams}`, {
		headers
	});
	const projectsListBody = await projectsListRes.json();

	if (!projectsListRes.ok) {
		logger.error('PROJECT_LIST_LIST', projectsListBody);
		return json(new APIError('Failed to get projects list', projectsListBody), {
			status: projectsListRes.status
		});
	} else {
		return json(projectsListBody);
	}
};

export const POST = async ({ cookies, fetch, locals, request }) => {
	const activeOrganizationId = cookies.get('activeOrganizationId');

	const { name: project_name } = await request.json();
	if (!project_name || typeof project_name !== 'string' || project_name.trim() === '') {
		return json(new APIError('Invalid project name'), { status: 400 });
	}

	if (!projectIDPattern.test(project_name)) {
		return json(
			new APIError(
				'Project name must contain only alphanumeric characters and underscores/hyphens/spaces/periods, and start and end with alphanumeric characters, between 2 and 100 characters.'
			),
			{ status: 400 }
		);
	}

	if (PUBLIC_IS_LOCAL === 'false') {
		//* Verify user perms
		if (!locals.user) {
			return json(new APIError('Unauthorized'), { status: 401 });
		}

		const userApiRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users/${locals.user.sub}`, {
			headers
		});
		const userApiBody = (await userApiRes.json()) as UserRead;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.member_of.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg || (targetOrg.role !== 'admin' && targetOrg.role !== 'member')) {
				return json(new APIError('Forbidden'), { status: 403 });
			}
		} else {
			logger.error('PROJECT_CREATE_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	const createProjectRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects`, {
		method: 'POST',
		headers: {
			...headers,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			name: project_name,
			organization_id: activeOrganizationId
		})
	});

	const createProjectBody = await createProjectRes.json();
	if (!createProjectRes.ok) {
		logger.error('PROJECT_CREATE_CREATE', createProjectBody);
		return json(new APIError('Failed to create project', createProjectBody), {
			status: createProjectRes.status
		});
	} else {
		return json(createProjectBody);
	}
};

export const PATCH = async ({ locals, request }) => {
	const { id: projectId, name: project_name } = await request.json();
	if (!project_name || typeof project_name !== 'string' || project_name.trim() === '') {
		return json(new APIError('Invalid project name'), { status: 400 });
	}

	if (PUBLIC_IS_LOCAL === 'false') {
		if (!locals.user) {
			return json(new APIError('Unauthorized'), { status: 401 });
		}

		const projectApiRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects/${projectId}`, {
			headers
		});
		const projectApiBody = await projectApiRes.json();

		if (!projectApiRes.ok) {
			logger.error('PROJECT_PATCH_GETPROJ', projectApiBody);
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
			logger.error('PROJECT_PATCH_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	const patchProjectRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects`, {
		method: 'PATCH',
		headers: {
			...headers,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			id: projectId,
			name: project_name
		})
	});

	const patchProjectBody = await patchProjectRes.json();
	if (!patchProjectRes.ok) {
		logger.error('PROJECT_PATCH_PATCH', patchProjectBody);
		return json(new APIError('Failed to update project', patchProjectBody as any), {
			status: patchProjectRes.status
		});
	} else {
		return json({ ok: true });
	}
};
