import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_URL, JAMAI_SERVICE_KEY } from '$env/static/private';
import { json } from '@sveltejs/kit';
import axios from 'axios';
import logger, { APIError } from '$lib/logger.js';
import type { UserRead } from '$lib/types.js';

const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

export const POST = async ({ locals, params, request }) => {
	const organizationId = params.organization_id;

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
			const targetOrg = userApiBody.member_of.find((org) => org.organization_id === organizationId);
			if (!targetOrg || targetOrg.role === 'guest') {
				return json(new APIError('Forbidden'), { status: 403 });
			}
		} else {
			logger.error('PROJECT_IMPORT_GETUSER', userApiBody);
			return json(new APIError('Failed to get user info', userApiBody as any), {
				status: userApiRes.status
			});
		}
	}

	try {
		const importProjectRes = await axios.post(
			`${JAMAI_URL}/api/admin/org/v1/projects/import/${organizationId}`,
			await request.formData(),
			{
				headers: {
					...headers,
					'Content-Type': 'multipart/form-data'
				}
			}
		);
		if (importProjectRes.status != 200) {
			logger.error('PROJECT_IMPORT_IMPORT', importProjectRes.data);
			return json(new APIError('Failed to import project', importProjectRes.data as any), {
				status: importProjectRes.status
			});
		} else {
			return new Response(importProjectRes.data);
		}
	} catch (err) {
		//@ts-expect-error AxiosError
		logger.error('PROJECT_IMPORT_IMPORT', err?.response?.data);
		//@ts-expect-error AxiosError
		return json(new APIError('Failed to import project', err?.response?.data), {
			status: 500
		});
	}
};
