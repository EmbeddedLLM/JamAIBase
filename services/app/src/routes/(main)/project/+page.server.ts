import { env } from '$env/dynamic/public';
import { env as privateEnv } from '$env/dynamic/private';
import { fail, redirect } from '@sveltejs/kit';
import type { UserRead } from '$lib/types.js';

const { PUBLIC_IS_LOCAL } = env;
const { JAMAI_URL, JAMAI_SERVICE_KEY } = privateEnv;

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export function load() {
	if (PUBLIC_IS_LOCAL !== 'false') {
		throw redirect(302, '/project/default/action-table');
	}
}

export const actions = {
	create: async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const project_name = data.get('project_name');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof project_name !== 'string' || project_name.trim() === '') {
			return fail(400, { message: 'Invalid project name' });
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, { message: 'Unauthorized' });
		}

		const userApiRes = await fetch(`${JAMAI_URL}/api/admin/v1/users/${locals.user.sub}`, {
			headers
		});
		const userApiBody = (await userApiRes.json()) as UserRead;
		if (userApiRes.ok) {
			const targetOrg = userApiBody.organizations.find(
				(org) => org.organization_id === activeOrganizationId
			);
			if (!targetOrg || (targetOrg.role !== 'admin' && targetOrg.role !== 'member')) {
				return fail(403, { message: 'Forbidden' });
			}
		} else {
			return fail(userApiRes.status, { message: 'API returned error', body: userApiBody });
		}

		const createProjectRes = await fetch(`${JAMAI_URL}/api/admin/v1/projects`, {
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
			return fail(createProjectRes.status, {
				message: 'API returned error',
				body: createProjectBody
			});
		} else {
			return createProjectBody;
		}
	}
};
