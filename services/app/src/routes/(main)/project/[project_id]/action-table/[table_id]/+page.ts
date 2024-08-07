import { PUBLIC_JAMAI_URL } from '$env/static/public';
import logger from '$lib/logger.js';
import { actionRowsPerPage } from '$lib/constants.js';
import type { GenTable, GenTableRow } from '$lib/types.js';

export const load = async ({ depends, fetch, params, parent, url }) => {
	depends('action-table:slug');
	await parent();
	const page = parseInt(url.searchParams.get('page') ?? '1');

	const getTable = async () => {
		const fetchPromises = [
			fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/${params.table_id}?` +
					new URLSearchParams({
						offset: '0',
						limit: '1'
					})
			),
			fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/${params.table_id}/rows?` +
					new URLSearchParams({
						offset: ((page - 1) * actionRowsPerPage).toString(),
						limit: actionRowsPerPage.toString()
					})
			)
		];

		const [responseTableData, responseRows] = await Promise.all(fetchPromises);
		const [tableData, rows] = await Promise.all([responseTableData.json(), responseRows.json()]);

		if (!responseTableData.ok || !responseRows.ok) {
			if (responseTableData.status !== 404 && responseTableData.status !== 422) {
				logger.error('ACTIONTBL_TBL_GET', { tableData, rows });
			}
			return { error: responseTableData.status, message: { tableData, rows } };
		} else {
			return {
				tableData: tableData as GenTable,
				rows: rows.items as GenTableRow[],
				total_rows: rows.total
			};
		}
	};

	return {
		table: params.table_id ? await getTable() : undefined
	};
};
