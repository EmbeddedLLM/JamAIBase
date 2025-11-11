import { env } from '$env/dynamic/private';
import { PUBLIC_ADMIN_ORGANIZATION_ID } from '$env/static/public';
import logger, { APIError } from '$lib/logger.js';
import type { ModelConfig } from '$lib/types.js';
import { error, fail } from '@sveltejs/kit';

const { OWL_URL, OWL_SERVICE_KEY } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ cookies, locals, depends, params }) {
	depends('system:modelsslug');

	if (!locals.user) {
		return error(401, 'Unauthorized');
	}

	if (
		cookies.get('activeOrganizationId') !== PUBLIC_ADMIN_ORGANIZATION_ID ||
		!locals.user?.org_memberships.find(
			(org) => org.organization_id === PUBLIC_ADMIN_ORGANIZATION_ID
		)
	) {
		throw error(404, 'Not found');
	}

	const getModelConfig = async () => {
		const response = await fetch(
			`${OWL_URL}/api/v2/models/configs?${new URLSearchParams([['model_id', params.model_id]])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user!.id || ''
				}
			}
		);

		const data = await response.json();

		if (!response.ok) {
			logger.error('MODELCONFIG_GET_ERROR', data, locals.user!.id);
			return { data: null, status: response.status, error: data as any };
		}

		return { data: data as ModelConfig, status: response.status };
	};

	return {
		modelConfig: getModelConfig()
	};
}

export const actions = {
	'edit-model-config': async function ({ locals, request }) {
		if (!locals.user) {
			return error(401, 'Unauthorized');
		}

		const formData = await request.formData();

		const data: Record<string, any> = {};

		try {
			for (const [key, value] of formData.entries()) {
				// Skip empty values
				if (value === '' || value === null || value === undefined) continue;

				// Handle value conversion
				const numValue = Number(value);
				if (!isNaN(numValue)) {
					data[key] = numValue;
				} else {
					data[key] = value;
				}
			}

			data['capabilities'] = JSON.parse((formData.get('capabilities') as string) || '[]');

			data['languages'] = JSON.parse((formData.get('languages') as string) || '[]');

			data['allowed_orgs'] = JSON.parse((formData.get('allowed_orgs') as string) || '[]');
			data['blocked_orgs'] = JSON.parse((formData.get('blocked_orgs') as string) || '[]');

			data['owned_by'] = (formData.get('owned_by') as string) || '';

			if (data['icon']) {
				if (!data['meta']) {
					data['meta'] = {};
				}
				data['meta']['icon'] = data['icon'];
				delete data['icon'];
			}

			const response = await fetch(
				`${OWL_URL}/api/v2/models/configs?${new URLSearchParams([['model_id', data.model_id]])}`,
				{
					method: 'PATCH',
					headers: {
						...headers,
						'x-user-id': locals.user.id || '',
						'Content-Type': 'application/json'
					},
					body: JSON.stringify(data)
				}
			);

			const responseData = await response.json();

			if (!response.ok) {
				logger.error('MODELCONFIG_EDIT_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to edit model config', responseData).getSerializable()
				);
			}

			return responseData;
		} catch (error) {
			logger.error('MODELCONFIG_EDIT_ERROR', error, locals.user.id);
			return fail(500, new APIError('Failed to edit model config', error as any).getSerializable());
		}
	}
};
