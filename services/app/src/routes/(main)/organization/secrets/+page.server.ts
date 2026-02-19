import { env } from '$env/dynamic/private';
import logger, { APIError } from '$lib/logger';
import type { SecretsRead } from '$lib/types';
import { fail } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ locals, parent }) {
	const data = await parent();

	const getOrgSecrets = async () => {
		const activeOrganizationId = data.organizationData?.id;
		if (!activeOrganizationId) {
			return { error: 400, message: 'No active organization' };
		}

		const orgSecretsRes = await fetch(
			`${OWL_URL}/api/v2/secrets/list?${new URLSearchParams([['organization_id', activeOrganizationId]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? ''
				}
			}
		);
		const orgSecretsBody = await orgSecretsRes.json();

		if (!orgSecretsRes.ok) {
			logger.error('ORGSECRETS_FETCH_ERROR', orgSecretsBody);
			return { error: orgSecretsRes.status, message: orgSecretsBody };
		} else {
			return {
				data: orgSecretsBody.items as SecretsRead[]
			};
		}
	};

	return {
		orgSecrets: getOrgSecrets()
	};
}

export const actions = {
	'update-org-secret': async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const newSecret = !!data.get('new');
		const name = data.get('name');
		const value = data.get('value');
		const allowed_projects = data.get('allowed_projects');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof name !== 'string' || name.trim() === '') {
			return fail(400, new APIError('Invalid secret name').getSerializable());
		}
		if (typeof value !== 'string' || value.trim() === '') {
			return fail(400, new APIError('Invalid secret value').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		if (newSecret) {
			const addOrgSecretRes = await fetch(
				`${OWL_URL}/api/v2/secrets?${new URLSearchParams([['organization_id', activeOrganizationId]])}`,
				{
					method: 'POST',
					headers: {
						...headers,
						'x-user-id': locals.user.id,
						'Content-Type': 'application/json'
					},
					body: JSON.stringify({
						name,
						value,
						// @ts-expect-error type
						allowed_projects: allowed_projects === null ? null : JSON.parse(allowed_projects)
					})
				}
			);

			const addOrgSecretBody = await addOrgSecretRes.json();
			if (!addOrgSecretRes.ok) {
				return fail(
					addOrgSecretRes.status,
					new APIError('Failed to add organization secret', addOrgSecretBody).getSerializable()
				);
			} else {
				return addOrgSecretBody;
			}
		} else {
			const updateOrgSecretRes = await fetch(
				`${OWL_URL}/api/v2/secrets?${new URLSearchParams([
					['organization_id', activeOrganizationId],
					['name', name]
				])}`,
				{
					method: 'PATCH',
					headers: {
						...headers,
						'x-user-id': locals.user.id,
						'Content-Type': 'application/json'
					},
					body: JSON.stringify({
						value,
						// @ts-expect-error type
						allowed_projects: allowed_projects === null ? null : JSON.parse(allowed_projects)
					})
				}
			);

			const updateOrgSecretBody = await updateOrgSecretRes.json();
			if (!updateOrgSecretRes.ok) {
				return fail(
					updateOrgSecretRes.status,
					new APIError(
						'Failed to update organization secret',
						updateOrgSecretBody
					).getSerializable()
				);
			} else {
				return updateOrgSecretBody;
			}
		}
	},

	'delete-org-secret': async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const name = data.get('name');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof name !== 'string' || name.trim() === '') {
			return fail(400, new APIError('Invalid secret name').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const deleteOrgSecretRes = await fetch(
			`${OWL_URL}/api/v2/secrets?${new URLSearchParams([
				['organization_id', activeOrganizationId],
				['name', name]
			])}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);

		const deleteOrgSecretBody = await deleteOrgSecretRes.json();
		if (!deleteOrgSecretRes.ok) {
			return fail(
				deleteOrgSecretRes.status,
				new APIError('Failed to delete organization secret', deleteOrgSecretBody).getSerializable()
			);
		} else {
			return deleteOrgSecretBody;
		}
	},

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
