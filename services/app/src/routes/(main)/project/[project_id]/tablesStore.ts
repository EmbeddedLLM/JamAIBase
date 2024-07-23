import { writable } from 'svelte/store';
import type { GenTable, GenTableRow } from '$lib/types';

export const genTableRows = createGenTableRows();
export const pastActionTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastKnowledgeTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastChatAgents = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastChatConversations = writable<Omit<GenTable, 'num_rows'>[]>([]);

function createGenTableRows() {
	const { subscribe, set, update } = writable<GenTableRow[] | undefined>(undefined);

	return {
		subscribe,
		set,
		/** Adds a row at the beginning of the array */
		addRow: (row: GenTableRow) =>
			update((rows) => {
				if (rows) {
					return [row, ...rows];
				} else {
					return rows;
				}
			}),
		/** Removes a row */
		deleteRow: (rowID: string) =>
			update((rows) => {
				if (rows) {
					return rows.filter((row) => row.ID !== rowID);
				} else {
					return rows;
				}
			}),
		/** Updates a row */
		updateRow: (rowID: string, data: GenTableRow) =>
			update((rows) =>
				rows?.map((row) => {
					if (row.ID === rowID) {
						return {
							...row,
							...data
						};
					}
					return row;
				})
			),
		/** Set cell value */
		setCell: ({ rowID, columnID }: { rowID: string; columnID: string }, value: any) =>
			update((rows) =>
				rows?.map((row) => {
					if (row.ID === rowID) {
						if (columnID === 'ID' || columnID === 'Updated at') {
							return {
								...row,
								[columnID]: value
							};
						} else {
							return {
								...row,
								[columnID]: {
									value: value
								}
							};
						}
					}
					return row;
				})
			),
		/** Streaming prep, clears outputs */
		clearOutputs: (tableData: GenTable, rowIDs: string[]) =>
			update((rows) =>
				rows?.map((row) => {
					if (rowIDs.includes(row.ID)) {
						return {
							...row,
							...Object.fromEntries(
								Object.entries(row).map(([key, value]) => {
									if (key === 'ID' || key === 'Updated at') {
										return [key, value as string];
									} else {
										return [
											key,
											{
												value: tableData.cols.find((col) => col.id == key)?.gen_config
													? ''
													: (value as { value: any }).value
											}
										];
									}
								})
							)
						};
					}
					return row;
				})
			),
		/** Stream to cell */
		stream: (rowID: string, colID: string, value: any) =>
			update((rows) =>
				rows?.map((row) => {
					if (row.ID === rowID) {
						return {
							...row,
							[colID]: {
								value: (row[colID]?.value ?? '') + value
							}
						};
					}
					return row;
				})
			),
		/** Revert to original value  */
		revert: (
			originalValues: {
				id: string;
				value: GenTableRow;
			}[]
		) =>
			update((rows) =>
				rows?.map((row) => {
					const originalRow = originalValues.find((o) => o.id === row.ID);
					if (originalRow) {
						return originalRow.value;
					}
					return row;
				})
			)
	};
}
