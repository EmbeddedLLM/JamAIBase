import { PUBLIC_JAMAI_URL } from '$env/static/public';
import { error } from '@sveltejs/kit';
import logger from '$lib/logger.js';
import { chatRowsPerPage } from '$lib/constants.js';
import type { GenTable, GenTableRow, ChatRequest } from '$lib/types.js';

export const load = async ({ depends, fetch, params, parent, url }) => {
	depends('chat-table:slug');
	await parent();
	const page = parseInt(url.searchParams.get('page') ?? '1');
	const orderAsc = parseInt(url.searchParams.get('asc') ?? '0');

	if (!params.table_id) {
		throw error(400, 'Missing table ID');
	}

	const getTable = async () => {
		const tableDataRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${params.table_id}?` +
				new URLSearchParams({
					offset: '0',
					limit: '1'
				}),
			{
				headers: {
					'x-project-id': params.project_id
				}
			}
		);
		const tableDataBody = await tableDataRes.json();

		if (!tableDataRes.ok) {
			if (tableDataRes.status !== 404 && tableDataRes.status !== 422) {
				logger.error('CHATTBL_TBL_GET', tableDataBody);
			}
			return { error: tableDataRes.status, message: tableDataBody };
		} else {
			return {
				data: tableDataBody as GenTable
			};
		}
	};

	const getRows = async () => {
		const tableRowsRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${params.table_id}/rows?` +
				new URLSearchParams({
					offset: ((page - 1) * chatRowsPerPage).toString(),
					limit: chatRowsPerPage.toString(),
					order_descending: orderAsc === 1 ? 'false' : 'true'
				}),
			{
				headers: {
					'x-project-id': params.project_id
				}
			}
		);
		const tableRowsBody = await tableRowsRes.json();

		if (!tableRowsRes.ok) {
			if (tableRowsRes.status !== 404 && tableRowsRes.status !== 422) {
				logger.error('CHATTBL_TBL_GETROWS', tableRowsBody);
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

	const getThread = async () => {
		const tableThreadRes = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${params.table_id}/thread?` +
				new URLSearchParams({
					column_id: 'AI'
				}),
			{
				headers: {
					'x-project-id': params.project_id
				}
			}
		);
		const tableThreadBody = await tableThreadRes.json();

		if (!tableThreadRes.ok) {
			if (tableThreadRes.status !== 404 && tableThreadRes.status !== 422) {
				logger.error('CHATTBL_TBL_GETTHREAD', tableThreadBody);
			}
			return { error: tableThreadRes.status, message: tableThreadBody };
		} else {
			return {
				data: tableThreadBody.thread as ChatRequest['messages']
			};
		}
	};

	return {
		table: getTable(),
		tableRows: getRows(),
		thread: getThread()
	};
};
