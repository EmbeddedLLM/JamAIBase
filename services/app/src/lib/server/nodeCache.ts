import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { JAMAI_SERVICE_KEY, JAMAI_URL } from '$env/static/private';
import NodeCache from 'node-cache';
import logger from '$lib/logger';
import type { PriceRes } from '$lib/types';

const nodeCache = new NodeCache();

export const getPrices = async () => {
	if (PUBLIC_IS_LOCAL !== 'false') return undefined;

	const cachedPrices = nodeCache.get<PriceRes>('prices');

	if (cachedPrices) return cachedPrices;

	const pricesRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/prices`, {
		headers: { Authorization: `Bearer ${JAMAI_SERVICE_KEY}` }
	});
	const pricesBody = (await pricesRes.json()) as PriceRes;

	if (!pricesRes.ok) {
		logger.error('APP_PRICES', pricesBody);
		return undefined;
	}

	nodeCache.set('prices', pricesBody, 1800);
	return pricesBody;
};

export default nodeCache;
