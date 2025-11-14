import { env } from '$env/dynamic/private';
import { PUBLIC_ADMIN_ORGANIZATION_ID } from '$env/static/public';
import logger, { APIError } from '$lib/logger.js';
import { error, fail } from '@sveltejs/kit';

const { OWL_URL, OWL_SERVICE_KEY } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ cookies, locals }) {
	if (
		cookies.get('activeOrganizationId') !== PUBLIC_ADMIN_ORGANIZATION_ID ||
		!locals.user?.org_memberships.find(
			(org) => org.organization_id === PUBLIC_ADMIN_ORGANIZATION_ID
		)
	) {
		throw error(404, 'Not found');
	}
}

export const actions = {
	'add-model-config': async function ({ locals, request }) {
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

			data['capabilities'] = JSON.parse(formData.get('capabilities') as string);
			if (data['languages']) {
				data['languages'] = JSON.parse(formData.get('languages') as string);
			}
			if (data.provisioned_to !== undefined && data.provisioned_to !== null) {
				data.provisioned_to = String(data.provisioned_to);
			}

			if (data['icon']) {
				if (!data['meta']) {
					data['meta'] = {};
				}
				data['meta']['icon'] = data['icon'];
				delete data['icon'];
			}

			const response = await fetch(`${OWL_URL}/api/v2/models/configs`, {
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': locals.user.id || '',
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(data)
			});

			const responseData = await response.json();

			if (!response.ok) {
				logger.error('MODELCONFIG_ADD_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to create model config', responseData).getSerializable()
				);
			}

			return responseData;
		} catch (error) {
			logger.error('MODELCONFIG_ADD_ERROR', error, locals.user.id);
			return fail(
				500,
				new APIError('Failed to create model config', error as any).getSerializable()
			);
		}
	},
	'delete-model-config': async function ({ locals, request }) {
		if (!locals.user) {
			return error(401, 'Unauthorized');
		}

		const formData = await request.formData();

		try {
			const model_id = formData.get('model_id')?.toString();

			if (!model_id || typeof model_id !== 'string' || model_id.trim() === '') {
				return fail(400, new APIError('Model ID (type string) is required').getSerializable());
			}

			const response = await fetch(
				`${OWL_URL}/api/v2/models/configs?${new URLSearchParams([['model_id', model_id]])}`,
				{
					method: 'DELETE',
					headers: {
						...headers,
						'x-user-id': locals.user.id || ''
					}
				}
			);

			const responseData = await response.json();

			if (!response.ok) {
				logger.error('MODELCONFIG_DELETE_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to delete model config', responseData).getSerializable()
				);
			}

			return responseData;
		} catch (error: any) {
			logger.error('MODELCONFIG_DELETE_ERROR', error, locals.user.id);
			return fail(
				500,
				new APIError('Failed to delete model config', error as any).getSerializable()
			);
		}
	},

	'add-deployment': async function ({ locals, request }) {
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

			const response = await fetch(`${OWL_URL}/api/v2/models/deployments/cloud`, {
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': locals.user.id || '',
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(data)
			});

			const responseData = await response.json();

			if (!response.ok) {
				logger.error('DEPLOYMENT_ADD_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to create deployment', responseData as any).getSerializable()
				);
			}

			return responseData;
		} catch (error) {
			logger.error('DEPLOYMENT_ADD_ERROR', error, locals.user.id);
			return fail(500, new APIError('Failed to create deployment', error as any).getSerializable());
		}
	},
	'edit-deployment': async function ({ locals, request }) {
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

			const response = await fetch(
				`${OWL_URL}/api/v2/models/deployments?${new URLSearchParams([['deployment_id', data.id]])}`,
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
				logger.error('DEPLOYMENT_EDIT_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to edit deployment', responseData).getSerializable()
				);
			}

			return responseData;
		} catch (error) {
			logger.error('DEPLOYMENT_EDIT_ERROR', error, locals.user.id);
			return fail(500, new APIError('Failed to edit deployment', error as any).getSerializable());
		}
	},
	'delete-deployment': async function ({ locals, request }) {
		if (!locals.user) {
			return error(401, 'Unauthorized');
		}

		const formData = await request.formData();

		try {
			const deployment_id = formData.get('deployment_id')?.toString();

			if (!deployment_id || typeof deployment_id !== 'string' || deployment_id.trim() === '') {
				return fail(400, new APIError('Deployment ID (type string) is required').getSerializable());
			}

			const response = await fetch(
				`${OWL_URL}/api/v2/models/deployments?${new URLSearchParams([['deployment_id', deployment_id]])}`,
				{
					method: 'DELETE',
					headers: {
						...headers,
						'x-user-id': locals.user.id || ''
					}
				}
			);

			const responseData = await response.json();

			if (!response.ok) {
				logger.error('DEPLOYMENT_DELETE_ERROR', responseData, locals.user.id);
				return fail(
					response.status,
					new APIError('Failed to delete deployment', responseData).getSerializable()
				);
			}

			return responseData;
		} catch (error) {
			logger.error('DEPLOYMENT_DELETE_ERROR', error, locals.user.id);
			return fail(500, new APIError('Failed to delete deployment', error as any).getSerializable());
		}
	}
};
