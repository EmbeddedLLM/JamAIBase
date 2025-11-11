import { env } from '$env/dynamic/private';
import logger from '$lib/logger.js';

const { OWL_URL, OWL_SERVICE_KEY } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ locals }) {
	const getProviders = async () => {
		const response = await fetch(`${OWL_URL}/api/v2/models/deployments/providers/cloud`, {
			headers: {
				...headers,
				'x-user-id': locals.user?.id || ''
			}
		});

		const responseBody = await response.json();

		if (!response.ok) {
			logger.error('PROVIDERS_GET_ERROR', responseBody, locals.user?.id);
			return { error: response.status, message: responseBody };
		}

		return { data: responseBody as string[] };
	};

	return {
		providers: getProviders()
	};
}
