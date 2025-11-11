import { env } from '$env/dynamic/private';
import logger, { APIError } from '$lib/logger.js';
import { json } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const GET = async ({ locals, url }) => {
	const projectId = url.searchParams.get('project_id');

	//* Verify user perms
	if (!locals.user) {
		return json(new APIError('Unauthorized'), { status: 401 });
	}

	const exportProjectRes = await fetch(
		`${OWL_URL}/api/v2/projects/export?${new URLSearchParams([['project_id', projectId ?? '']])}`,
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
