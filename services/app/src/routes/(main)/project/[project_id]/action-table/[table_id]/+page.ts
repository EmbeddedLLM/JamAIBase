import { PUBLIC_JAMAI_URL } from '$env/static/public';
import { actionRowsPerPage } from '$lib/constants.js';
import logger from '$lib/logger.js';
import type { GenTable, GenTableRow } from '$lib/types.js';
import { error } from '@sveltejs/kit';

export const load = async ({ depends, fetch, params, parent, url }) => {
	depends('action-table:slug');
	await parent();
	const page = parseInt(url.searchParams.get('page') ?? '1');
	const orderBy = url.searchParams.get('sort_by');
	const orderAsc = parseInt(url.searchParams.get('asc') ?? '0');

	if (!params.table_id) {
		throw error(400, 'Missing table ID');
	}

	const getTable = async () => {
		const tableDataRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/action?${new URLSearchParams([['table_id', params.table_id]])}`,
			{
				headers: {
					'x-project-id': params.project_id
				}
			}
		);
		const tableDataBody = await tableDataRes.json();

		if (!tableDataRes.ok) {
			if (![403, 404, 422].includes(tableDataRes.status)) {
				logger.error('ACTIONTBL_TBL_GET', tableDataBody);
			}
			return { error: tableDataRes.status, message: tableDataBody };
		} else {
			return {
				data: tableDataBody as GenTable
			};
		}
	};

	const getRows = async () => {
		const q = url.searchParams.get('q');

		const searchParams = new URLSearchParams([
			['table_id', params.table_id],
			['offset', ((page - 1) * actionRowsPerPage).toString()],
			['limit', actionRowsPerPage.toString()],
			['order_by', orderBy ?? 'ID'],
			['order_ascending', orderAsc === 1 ? 'true' : 'false']
		]);

		if (q) {
			searchParams.set('search_query', q);
		}

		const tableRowsRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/action/rows/list?${searchParams}`,
			{
				headers: {
					'x-project-id': params.project_id
				}
			}
		);
		const tableRowsBody = await tableRowsRes.json();

		if (!tableRowsRes.ok) {
			if (![403, 404, 422].includes(tableRowsRes.status)) {
				logger.error('ACTIONTBL_TBL_GETROWS', tableRowsBody);
			}
			return { error: tableRowsRes.status, message: tableRowsBody };
		} else {
			return {
				data: {
					rows: tableRowsBody.items as GenTableRow[],
					total_rows: tableRowsBody.total as number
				}
			};
		}
	};

	return {
		table: getTable(),
		tableRows: getRows()
	};
};
