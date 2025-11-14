import { env } from '$env/dynamic/private';
import logger from '$lib/logger.js';
import { error, redirect } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const load = async ({ locals, url, parent }) => {
	await parent();
	const token = url.searchParams.get('token');

	if (token) {
		if (!locals.user) {
			throw error(401, 'Unauthorized');
		}

		const inviteUserRes = await fetch(
			`${OWL_URL}/api/v2/projects/members?${new URLSearchParams([
				['user_id', locals.user.id],
				['invite_code', token]
			])}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? ''
				}
			}
		);

		const inviteUserBody = await inviteUserRes.json();
		if (!inviteUserRes.ok) {
			if (inviteUserRes.status !== 404) {
				logger.error('INVITEPROJ_TOKEN_ERROR', inviteUserBody);
			}
			throw error(inviteUserRes.status, inviteUserBody.message || JSON.stringify(inviteUserBody));
		} else {
			throw redirect(302, '/');
		}
	}
};

export const actions = {
	/** Form actions method of invite */
	// default: async function ({ locals, request }) {
	// 	if (!locals.uer) {
	// 		return error(401, 'Unauthorized');
	// 	}
	// 	const formdata = await request.formData();
	// 	const code = formdata.get('code');
	// 	if (!code || typeof code !== 'string' || code.trim() === '') {
	// 		return fail(400, new APIError('Code (type string) is required').getSerializable());
	// 	}
	// 	const response = await fetch(
	// 		`${OWL_URL}/api/v2/organizations/members?${new URLSearchParams([
	// 			['user_id', locals.user?.id ?? ''],
	// 			['invite_code', code]
	// 		])}`,
	// 		{
	// 			method: 'POST',
	// 			headers: {
	// 				...headers,
	// 				// 'x-user-id': locals.user.id || '',
	// 				'Content-Type': 'application/json'
	// 			}
	// 		}
	// 	);
	// 	const responseBody = await response.json();
	// 	if (response.ok) {
	// 		return responseBody?.organization;
	// 	}
	// 	return fail(
	// 		response.status,
	// 		new APIError('Failed to join organization', responseBody).getSerializable()
	// 	);
	// }
};
