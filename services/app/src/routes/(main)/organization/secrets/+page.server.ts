import { env } from '$env/dynamic/private';
import { APIError } from '$lib/logger.js';
import { fail } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const actions = {
	'update-external-keys': async ({ cookies, fetch, locals, request }) => {
		const activeOrganizationId = cookies.get('activeOrganizationId');

		const data = await request.formData();
		const externalKeys: Record<string, string> = {};
		for (const [key, value] of data.entries()) {
			externalKeys[key] = (value as string).trim();
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const updateExternalKeysRes = await fetch(
			`${OWL_URL}/api/v2/organizations?${new URLSearchParams([['organization_id', activeOrganizationId]])}`,
			{
				method: 'PATCH',
				headers: {
					...headers,
					'x-user-id': locals.user.id,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					external_keys: externalKeys
				})
			}
		);

		const updateExternalKeysBody = await updateExternalKeysRes.json();
		if (!updateExternalKeysRes.ok) {
			return fail(
				updateExternalKeysRes.status,
				new APIError('Failed to update external keys', updateExternalKeysBody).getSerializable()
			);
		} else {
			return updateExternalKeysBody;
		}
	}
};
