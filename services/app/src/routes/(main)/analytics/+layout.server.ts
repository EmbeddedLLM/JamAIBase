import { error } from '@sveltejs/kit';
import { addMonths, differenceInMonths, fromUnixTime } from 'date-fns';

export const load = async ({ depends, locals, parent, url }) => {
	await parent();
	depends('app:usage-token');

	if (!locals.user) {
		throw error(401, 'Unauthorized');
	}

	let month = parseInt(url.searchParams.get('month') ?? '');

	if (url.searchParams.get('month') && isNaN(month)) {
		throw error(400, 'Invalid month');
	}

	if (!month) {
		month = differenceInMonths(new Date(), fromUnixTime(0));
	}

	if (month > 5000) {
		throw error(400, 'Invalid month');
	}

	const fromDate = addMonths(fromUnixTime(0), month);
	const toDate = addMonths(fromDate, 1);
	toDate.setUTCMinutes(0);
	toDate.setUTCSeconds(0);
	toDate.setUTCMilliseconds(0);

	return {
		fromDate,
		toDate
	};
};
