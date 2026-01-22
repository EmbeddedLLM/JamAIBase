import { env } from '$env/dynamic/private';
import logger from '$lib/logger.js';
import { fillMissingDaysForUsage } from '$lib/server/utils.js';
import {
	bandwidthUsageSchema,
	baseUsageSchema,
	storageUsageSchema,
	tokenUsageSchema,
	type TUsageData,
	type TUsageDataStorage
} from '$lib/types';
import { error } from '@sveltejs/kit';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const load = async ({ depends, locals, parent }) => {
	const data = await parent();
	const { organizationData, fromDate, toDate } = data;
	depends('app:dashboard');

	if (!locals.user) {
		throw error(401, 'Unauthorized');
	}

	const fetchTokenUsageByType = (
		type: 'llm' | 'image' | 'embedding' | 'reranking',
		logKey: string
	): ((
	) => Promise<{
		data: TUsageData[] | null;
		status: number;
		error?: any;
	}>) => {
		return async () => {
			if (!organizationData) {
				return { data: null, status: 400, error: 'No active organization' };
			}
			let usageData: TUsageData[] = [];

			const response = await fetch(
				`${OWL_URL}/api/v2/meters/usages?${new URLSearchParams([
					['type', type],
					['from', fromDate.toISOString()],
					['to', toDate.toISOString()],
					['orgIds', organizationData.id],
					['windowSize', '1d'],
					['groupBy', 'model']
				])}`,
				{
					headers: {
						...headers,
						'x-user-id': locals.user?.id ?? '',
						'Content-Type': 'application/json'
					}
				}
			);
			const responseBody = await response.json();

			if (!response.ok) {
				if (![403].includes(response.status)) {
					logger.error(logKey, responseBody);
				}
				return { data: null, status: 500, error: responseBody };
			}

			let tokenUsageData;
			try {
				tokenUsageData = tokenUsageSchema.parse(responseBody.data);
			} catch (err) {
				throw { data: null, status: 500, error: 'Parsing error' };
			}

			const groups: { [key: string]: TUsageData } = {};

			tokenUsageData.forEach((item) => {
				const {
					value,
					window_start,
					groupBy: { model }
				} = item;
				if (!groups[model]) {
					groups[model] = {
						model,
						data: []
					};
				}
				groups[model].data.push({ date: window_start, amount: value });
			});

			usageData = Object.values(groups);

			// if there is no data for the selected month, populate with 1 data point to display an empty chart
			if (usageData.length === 0) {
				usageData.push({
					model: '',
					data: [{ amount: 0, date: fromDate.toISOString() }]
				});
			}

			usageData = usageData.map((item) => ({
				...item,
				data: fillMissingDaysForUsage(item.data, fromDate.toISOString())
			}));

			return { data: usageData, status: 200 };
		};
	};

	const fetchLlmTokenUsage = fetchTokenUsageByType('llm', 'TOKENUSAGE_FETCH_ERROR');
	const fetchImageTokenUsage = fetchTokenUsageByType('image', 'IMAGE_TOKENUSAGE_FETCH_ERROR');
	const fetchEmbeddingTokenUsage = fetchTokenUsageByType(
		'embedding',
		'EMBED_TOKENUSAGE_FETCH_ERROR'
	);
	const fetchRerankingTokenUsage = fetchTokenUsageByType(
		'reranking',
		'RERANK_TOKENUSAGE_FETCH_ERROR'
	);

	const fetchStorageUsage: () => Promise<{
		data: TUsageDataStorage[] | null;
		status: number;
		error?: any;
	}> = async () => {
		if (!organizationData) {
			return { data: null, status: 400, error: 'No active organization' };
		}
		let usageData: TUsageDataStorage[] = [];

		const response = await fetch(
			`${OWL_URL}/api/v2/meters/storages?${new URLSearchParams([
				['from', fromDate.toISOString()],
				['to', toDate.toISOString()],
				['orgIds', organizationData.id],
				['windowSize', '1d'],
				['groupBy', 'type']
			])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? '',
					'Content-Type': 'application/json'
				}
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			if (![403].includes(response.status)) {
				logger.error('STORAGEUSAGE_FETCH_ERROR', responseBody);
			}
			return { data: null, status: 500, error: responseBody };
		}

		let storageUsageData;
		try {
			storageUsageData = storageUsageSchema.parse(responseBody.data);
		} catch (err) {
			throw { data: null, status: 500, error: 'Parsing error' };
		}

		const groups: { [key: string]: TUsageDataStorage } = {};

		storageUsageData.forEach((item) => {
			const {
				value,
				window_start,
				groupBy: { type }
			} = item;
			if (!groups[type]) {
				groups[type] = {
					type,
					data: []
				};
			}
			groups[type].data.push({ date: window_start, amount: value });
		});

		usageData = Object.values(groups);

		// if there is no data for the selected month, populate with 1 data point to display an empty chart
		if (usageData.length === 0) {
			usageData.push({
				type: '',
				data: [{ amount: 0, date: fromDate.toISOString() }]
			});
		}

		usageData = usageData.map((item) => ({
			...item,
			data: fillMissingDaysForUsage(item.data, fromDate.toISOString())
		}));

		return { data: usageData, status: 200 };
	};

	const fetchEgressUsage: () => Promise<{
		data: TUsageData['data'] | null;
		status: number;
		error?: any;
	}> = async () => {
		if (!organizationData) {
			return { data: null, status: 400, error: 'No active organization' };
		}
		let usageData: TUsageData['data'] = [];

		const response = await fetch(
			`${OWL_URL}/api/v2/meters/bandwidths?${new URLSearchParams([
				['from', fromDate.toISOString()],
				['to', toDate.toISOString()],
				['orgIds', organizationData.id],
				['windowSize', '1d'],
				['groupBy', 'type']
			])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? '',
					'Content-Type': 'application/json'
				}
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			if (![403].includes(response.status)) {
				logger.error('EGRESSUSAGE_FETCH_ERROR', responseBody);
			}
			return { data: null, status: 500, error: responseBody };
		}

		let egressUsageData;
		try {
			egressUsageData = bandwidthUsageSchema.parse(responseBody.data);
		} catch (err) {
			return { data: null, status: 500, error: 'Parsing error' };
		}

		usageData = egressUsageData
			.map(({ value, window_start, groupBy: { type } }) => {
				if (type === 'egress') return { date: window_start, amount: value };
				else return [];
			})
			.flat();

		usageData = fillMissingDaysForUsage(usageData, fromDate.toISOString());

		return { data: usageData, status: 200 };
	};

	//TODO: Differentiate input and output credits
	const fetchCreditUsage: () => Promise<{
		data: TUsageData['data'] | null;
		status: number;
		error?: any;
	}> = async () => {
		if (!organizationData) {
			return { data: null, status: 400, error: 'No active organization' };
		}
		let usageData: TUsageData['data'] = [];

		const response = await fetch(
			`${OWL_URL}/api/v2/meters/billings?${new URLSearchParams([
				['from', fromDate.toISOString()],
				['to', toDate.toISOString()],
				['orgIds', organizationData.id],
				['windowSize', '1d']
				// ['groupBy', 'type']
			])}`,
			{
				headers: {
					...headers,
					'x-user-id': locals.user?.id ?? '',
					'Content-Type': 'application/json'
				}
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			if (![403].includes(response.status)) {
				logger.error('CREDITUSAGE_FETCH_ERROR', responseBody);
			}
			return { data: null, status: 500, error: responseBody };
		}

		let creditUsageData;
		try {
			creditUsageData = baseUsageSchema.parse(responseBody.data);
		} catch (err) {
			return { data: null, status: 500, error: 'Parsing error' };
		}

		usageData = creditUsageData.map(({ value, window_start }) => {
			return { date: window_start, amount: value };
		});

		usageData = fillMissingDaysForUsage(usageData, fromDate.toISOString());

		return { data: usageData, status: 200 };
	};

	return {
		tokenUsage: fetchLlmTokenUsage(),
		imageTokenUsage: fetchImageTokenUsage(),
		embeddingTokenUsage: fetchEmbeddingTokenUsage(),
		rerankingTokenUsage: fetchRerankingTokenUsage(),
		creditUsage: fetchCreditUsage(),
		egressUsage: fetchEgressUsage(),
		storageUsage: fetchStorageUsage()
	};
};
