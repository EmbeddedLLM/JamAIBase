import { env } from '$env/dynamic/private';
import logger, { APIError } from '$lib/logger.js';
import { json } from '@sveltejs/kit';
import axios from 'axios';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const POST = async ({ locals, request }) => {
	//* Verify user perms
	if (!locals.user) {
		return json(new APIError('Unauthorized'), { status: 401 });
	}

	try {
		const importProjectRes = await axios.post(
			`${OWL_URL}/api/v2/projects/import/parquet`,
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
