import { writable } from 'svelte/store';
import { persisted } from 'svelte-persisted-store';
import { serializer } from '$lib/utils';
import type { GenTable, GenTableCol, GenTableRow } from '$lib/types';

export const tableState = createTableStore();
export const genTableRows = createGenTableRows();
export const pastActionTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastKnowledgeTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastChatAgents = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const chatTableMode = persisted<'chat' | 'table'>('table_mode', 'table', {
	serializer,
	storage: 'session'
});

interface TableState {
	templateCols: string;
	colSizes: Record<string, number>;
	resizingCol: { columnID: string; diffX: number } | null;
	editingCell: { rowID: string; columnID: string } | null;
	selectedRows: string[];
	streamingRows: Record<string, string[]>;
	columnSettings: {
		isOpen: boolean;
		column: GenTableCol | null;
	};
	renamingCol: string | null;
	deletingCol: string | null;
}

function createTableStore() {
	const defaultValue = {
		templateCols: '',
		colSizes: {},
		resizingCol: null,
		editingCell: null,
		selectedRows: [],
		streamingRows: {},
		columnSettings: {
			isOpen: false,
			column: null
		},
		renamingCol: null,
		deletingCol: null
	} satisfies TableState;
	const { subscribe, set, update } = writable<TableState>(defaultValue);

	return {
		subscribe,
		set,
		setTemplateCols: (columns: GenTableCol[]) =>
			update((state) => ({
				...state,
				templateCols: columns
					.filter((col) => col.id !== 'ID' && col.id !== 'Updated at')
					.map((col) => {
						const colSize = state.colSizes[col.id];
						if (colSize) return `${colSize}px`;
						else return 'minmax(320px, 1fr)';
					})
					.join(' ')
			})),
		setColSize: (colID: string, value: number) =>
			update((state) => {
				const obj = structuredClone(state);
				obj.colSizes[colID] = value;
				return obj;
			}),
		setResizingCol: (value: TableState['resizingCol']) =>
			update((state) => ({ ...state, resizingCol: value })),
		setEditingCell: (cell: TableState['editingCell']) =>
			update((state) => ({ ...state, editingCell: cell })),
		toggleRowSelection: (rowID: string) =>
			update((state) => ({
				...state,
				selectedRows: state.selectedRows.includes(rowID)
					? state.selectedRows.filter((id) => id !== rowID)
					: [...state.selectedRows, rowID]
			})),
		selectAllRows: (tableRows: GenTableRow[]) =>
			update((state) => ({
				...state,
				selectedRows: tableRows.every((row) => state.selectedRows.includes(row.ID))
					? state.selectedRows.filter((i) => !tableRows?.some(({ ID }) => ID === i))
					: [
							...state.selectedRows.filter((i) => !tableRows?.some(({ ID }) => ID === i)),
							...tableRows.map(({ ID }) => ID)
						]
			})),
		setSelectedRows: (rows: TableState['selectedRows']) =>
			update((state) => ({ ...state, selectedRows: rows })),
		addStreamingRows: (rows: TableState['streamingRows']) =>
			update((state) => ({ ...state, streamingRows: { ...state.streamingRows, ...rows } })),
		delStreamingRows: (rowIDs: string[]) =>
			update((state) => ({
				...state,
				streamingRows: Object.fromEntries(
					Object.entries(state.streamingRows).filter(([rowId]) => !rowIDs.includes(rowId))
				)
			})),
		setColumnSettings: (value: TableState['columnSettings']) =>
			update((state) => ({ ...state, columnSettings: value })),
		setRenamingCol: (value: string | null) => update((state) => ({ ...state, renamingCol: value })),
		setDeletingCol: (value: string | null) => update((state) => ({ ...state, deletingCol: value })),
		reset: () => set(defaultValue)
	};
}

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
		clearOutputs: (tableData: GenTable, rowIDs: string[], columnIDs?: string[]) =>
			update((rows) =>
				rows?.map((row) => {
					if (rowIDs.includes(row.ID)) {
						return {
							...row,
							...Object.fromEntries(
								Object.entries(row).map(([key, value]) => {
									if (
										key === 'ID' ||
										key === 'Updated at' ||
										(columnIDs && !columnIDs.includes(key))
									) {
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
