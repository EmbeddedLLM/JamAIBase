import { env } from '$env/dynamic/private';
import logger from '$lib/logger';
import type { PriceRes } from '$lib/types';
import NodeCache from 'node-cache';

const { OWL_SERVICE_KEY, OWL_URL } = env;

const nodeCache = new NodeCache();

export const getPrices = async (userId?: string) => {
	//? ossMode
	if (!OWL_SERVICE_KEY) return undefined;

	// const cachedPrices = nodeCache.get<PriceRes[]>('prices');

	// if (cachedPrices) return cachedPrices;

	const pricesRes = await fetch(
		`${OWL_URL}/api/v2/prices/plans/list?${new URLSearchParams([
			['order_by', 'flat_cost'],
			['order_ascending', 'true']
		])}`,
		{
			headers: userId ? { Authorization: `Bearer ${OWL_SERVICE_KEY}`, 'x-user-id': userId } : {}
		}
	);
	const pricesBody = await pricesRes.json();

	if (!pricesRes.ok) {
		logger.error('APP_PRICES', pricesBody);
		return undefined;
	}

	// nodeCache.set('prices', pricesBody.items as PriceRes[], 1);
	return pricesBody.items as PriceRes[];
};

export default nodeCache;
