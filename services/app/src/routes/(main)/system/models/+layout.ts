import { PUBLIC_JAMAI_URL } from '$env/static/public';
import { activeOrganization } from '$globalStore';
import logger from '$lib/logger.js';
import type { ModelConfig, ModelDeployment } from '$lib/types.js';
import { get } from 'svelte/store';

export const ssr = false;

export async function load({ data, depends, fetch }) {
	depends('system:models');

	//TODO: Maybe paginate this
	const getModelConfigs = async () => {
		const activeOrg = get(activeOrganization);

		const limit = 1000;
		const offset = 0;
		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/models/configs/list?${new URLSearchParams({
				organization_id: activeOrg?.id ?? '',
				offset: offset.toString(),
				limit: limit.toString()
			})}`
		);
		const responseBody = await response.json();

		if (!response.ok) {
			logger.error('MODELCONFIGS_GET_ERROR', responseBody);
			return { data: null, error: responseBody as any, status: response.status };
		}

		return { data: responseBody.items as ModelConfig[] };
	};

	const getDeployments = async () => {
		const limit = 1000;
		const offset = 0;
		const response = await fetch(
			`/api/owl/models/deployments/list?${new URLSearchParams([
				['offset', offset.toString()],
				['limit', limit.toString()]
			])}`
		);
		const responseBody = await response.json();

		if (!response.ok) {
			logger.error('DEPLOYMENTS_GET_ERROR', data);
			return { data: null, error: responseBody as any, status: response.status };
		}

		return { data: responseBody.items as ModelDeployment[] };
	};

	const getModelPresets = async () => {
		const response = await fetch(
			'https://raw.githubusercontent.com/EmbeddedLLM/JamAIBase/refs/heads/main/services/api/src/owl/configs/preset_models.json',
			{
				method: 'GET'
			}
		);

		if (!response.ok) {
			const error = await response.text();
			logger.error('MODELPRESETS_GET_ERROR', error);
			return { error: response.status, message: 'Failed to fetch model presets' };
		}

		return { data: (await response.json()) as ModelConfig[] };
	};

	return {
		...data,
		modelConfigs: getModelConfigs(),
		deployments: getDeployments(),
		modelPresets: await getModelPresets()
	};
}
