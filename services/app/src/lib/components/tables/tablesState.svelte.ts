import type { GenTable, GenTableCol, GenTableRow } from '$lib/types';
import { serializer } from '$lib/utils';
import { getContext, setContext } from 'svelte';
import { persisted } from 'svelte-persisted-store';
import { writable } from 'svelte/store';

export const pastActionTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastKnowledgeTables = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const pastChatAgents = writable<Omit<GenTable, 'num_rows'>[]>([]);
export const chatTableMode = persisted<'chat' | 'table'>('table_mode', 'table', {
	serializer,
	storage: 'session'
});

interface ITableState {
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
	setTemplateCols: (columns: GenTableCol[]) => void;
	setColSize: (colID: string, value: number) => void;
	setResizingCol: (value: ITableState['resizingCol']) => void;
	setEditingCell: (cell: ITableState['editingCell']) => void;
	toggleRowSelection: (rowID: string) => void;
	selectAllRows: (tableRows: GenTableRow[]) => void;
	setSelectedRows: (rows: ITableState['selectedRows']) => void;
	addStreamingRows: (rows: ITableState['streamingRows']) => void;
	delStreamingRows: (rowIDs: string[]) => void;
	setColumnSettings: (value: ITableState['columnSettings']) => void;
	setRenamingCol: (value: string | null) => void;
	setDeletingCol: (value: string | null) => void;
	reset: () => void;
}

export class TableState implements ITableState {
	templateCols = $state<string>('');
	colSizes = $state<Record<string, number>>({});
	resizingCol = $state<{ columnID: string; diffX: number } | null>(null);
	editingCell = $state<{ rowID: string; columnID: string } | null>(null);
	selectedRows = $state<string[]>([]);
	streamingRows = $state<Record<string, string[]>>({});
	columnSettings = $state<{
		isOpen: boolean;
		column: GenTableCol | null;
	}>({
		isOpen: false,
		column: null
	});
	addingCol = $state(false);
	renamingCol = $state<string | null>(null);
	deletingCol = $state<string | null>(null);

	constructor() {
		this.templateCols = '';
		this.colSizes = {};
		this.resizingCol = null;
		this.editingCell = null;
		this.selectedRows = [];
		this.streamingRows = {};
		this.columnSettings = {
			isOpen: false,
			column: null
		};
		this.renamingCol = null;
		this.deletingCol = null;
	}

	setTemplateCols(columns: GenTableCol[]) {
		this.templateCols = columns
			.filter((col) => col.id !== 'ID' && col.id !== 'Updated at')
			.map((col) => {
				const colSize = this.colSizes[col.id];
				if (colSize) return `${colSize}px`;
				else return 'minmax(320px, 1fr)';
			})
			.join(' ');
	}

	setColSize(colID: string, value: number) {
		// const obj = structuredClone(state);
		this.colSizes[colID] = value;
	}

	setResizingCol(value: TableState['resizingCol']) {
		this.resizingCol = value;
	}

	setEditingCell(cell: TableState['editingCell']) {
		this.editingCell = cell;
	}

	toggleRowSelection(rowID: string) {
		if (this.selectedRows.includes(rowID)) {
			this.selectedRows = this.selectedRows.filter((id) => id !== rowID);
		} else {
			this.selectedRows = [...this.selectedRows, rowID];
		}
	}

	selectAllRows(tableRows: GenTableRow[]) {
		if (tableRows.every((row) => this.selectedRows.includes(row.ID))) {
			this.selectedRows = this.selectedRows.filter((i) => !tableRows?.some(({ ID }) => ID === i));
		} else {
			this.selectedRows = [
				...this.selectedRows.filter((i) => !tableRows?.some(({ ID }) => ID === i)),
				...tableRows.map(({ ID }) => ID)
			];
		}
	}

	setSelectedRows(rows: TableState['selectedRows']) {
		this.selectedRows = rows;
	}

	addStreamingRows(rows: TableState['streamingRows']) {
		this.streamingRows = { ...this.streamingRows, ...rows };
	}

	delStreamingRows(rowIDs: string[]) {
		this.streamingRows = Object.fromEntries(
			Object.entries(this.streamingRows).filter(([rowId]) => !rowIDs.includes(rowId))
		);
	}

	setColumnSettings(value: TableState['columnSettings']) {
		this.columnSettings = $state.snapshot(value);
	}

	setRenamingCol(value: string | null) {
		this.renamingCol = value;
	}

	setDeletingCol(value: string | null) {
		this.deletingCol = value;
	}

	reset() {
		this.templateCols = '';
		this.colSizes = {};
		this.resizingCol = null;
		this.editingCell = null;
		this.selectedRows = [];
		this.streamingRows = {};
		this.columnSettings = {
			isOpen: false,
			column: null
		};
		this.renamingCol = null;
		this.deletingCol = null;
	}
}

const tableStateContextKey = 'tableState';
export function setTableState() {
	return setContext(tableStateContextKey, new TableState());
}

export function getTableState() {
	return getContext<TableState>(tableStateContextKey);
}

export class TableRowsState {
	rows = $state<GenTableRow[] | undefined>(undefined);
	loading = $state<boolean>(false);

	setRows(rows: GenTableRow[] | undefined) {
		this.rows = rows;
		this.loading = false;
	}

	/** Adds a row at the beginning of the array */
	addRow(row: GenTableRow) {
		this.rows = [row, ...(this.rows ?? [])];
	}

	/** Removes a row */
	deleteRow(rowID: string) {
		this.rows = this.rows?.filter((row) => row.ID !== rowID);
	}

	/** Updates a row */
	updateRow(rowID: string, data: GenTableRow) {
		this.rows = this.rows?.map((row) => {
			if (row.ID === rowID) {
				return { ...row, ...data };
			}
			return row;
		});
	}

	/** Set cell value */
	setCell({ rowID, columnID }: { rowID: string; columnID: string }, value: any) {
		this.rows = this.rows?.map((row) => {
			if (row.ID === rowID) {
				if (columnID === 'ID' || columnID === 'Updated at') {
					return { ...row, [columnID]: value };
				} else {
					return { ...row, [columnID]: { value: value } };
				}
			}
			return row;
		});
	}

	/** Streaming prep, clears outputs */
	clearOutputs(tableData: GenTable, rowIDs: string[], columnIDs?: string[]) {
		this.rows = this.rows?.map((row) => {
			if (rowIDs.includes(row.ID)) {
				return {
					...row,
					...Object.fromEntries(
						Object.entries(row).map(([key, value]) => {
							if (key === 'ID' || key === 'Updated at' || (columnIDs && !columnIDs.includes(key))) {
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
		});
	}

	/** Stream to cell */
	stream(rowID: string, colID: string, value: any) {
		this.rows = this.rows?.map((row) => {
			if (row.ID === rowID) {
				return {
					...row,
					[colID]: {
						value: (row[colID]?.value ?? '') + value
					}
				};
			}
			return row;
		});
	}

	/** Revert to original value  */
	revert(
		originalValues: {
			id: string;
			value: GenTableRow;
		}[]
	) {
		this.rows = this.rows?.map((row) => {
			const originalRow = originalValues.find((o) => o.id === row.ID);
			if (originalRow) {
				return originalRow.value;
			}
			return row;
		});
	}
}

const tableRowsStateContextKey = 'tableRowsState';
export function setTableRowsState() {
	return setContext(tableRowsStateContextKey, new TableRowsState());
}

export function getTableRowsState() {
	return getContext<TableRowsState>(tableRowsStateContextKey);
}
