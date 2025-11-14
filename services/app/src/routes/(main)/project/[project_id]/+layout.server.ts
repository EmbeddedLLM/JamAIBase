import { env } from '$env/dynamic/private';
import logger from '$lib/logger.js';
import type { ProjectMemberRead } from '$lib/types.js';

const { OWL_URL, OWL_SERVICE_KEY /* RESEND_API_KEY */ } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ cookies, locals }) {
	//TODO: Paginate this
	const getProjectMembers = async () => {
		const activeProjectId = cookies.get('activeProjectId');

		if (!activeProjectId) {
			return { error: 400, message: 'No active project' };
		}

		const response = await fetch(
			`${OWL_URL}/api/v2/projects/members/list?${new URLSearchParams([
				['project_id', activeProjectId]
			])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? ''
				}
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			logger.error('ORGMEMBER_LIST_ERROR', responseBody, locals.user?.id);
			return { error: response.status, message: responseBody };
		}

		return { data: responseBody.items as ProjectMemberRead[] };
	};

	return {
		projectMembers: getProjectMembers()
	};
}
