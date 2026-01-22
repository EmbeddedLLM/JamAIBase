import logger from '$lib/logger';
import type {
	ChatReferences,
	GenTable,
	GenTableCol,
	GenTableRow,
	GenTableStreamEvent,
	ReferenceChunk
} from '$lib/types';
import { escapeHtmlText, serializer } from '$lib/utils';
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
	tableData: GenTable | undefined;
	rowThumbs: { [rowID: string]: { [colID: string]: { value: string; url: string } } };
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
	deletingFile: { rowID: string; columnID: string; fileUri?: string } | null;
	showOutputDetails: {
		open: boolean;
		activeTab: string;
		message: {
			content: string;
			chunks: ReferenceChunk[];
		} | null;
		reasoningContent: string | null;
		reasoningTime: number | null;
		expandChunk: string | null;
		preview: ReferenceChunk | null;
	};
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
	tableData = $state<GenTable | undefined>();
	rowThumbs = $state<{ [rowID: string]: { [colID: string]: { value: string; url: string } } }>({});

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
	deletingFile = $state<{ rowID: string; columnID: string; fileUri?: string } | null>(null);

	/** Output details */
	showOutputDetails = $state<{
		open: boolean;
		activeCell: { rowID: string; columnID: string } | null;
		activeTab: string;
		message: {
			content: string;
			error: { message?: string } | string | null;
			chunks: ReferenceChunk[];
			fileUrl?: string;
		} | null;
		reasoningContent: string | null;
		reasoningTime: number | null;
		expandChunk: string | null;
		preview: ReferenceChunk | null;
	}>({
		open: false,
		activeCell: null,
		activeTab: 'answer',
		message: null,
		reasoningContent: null,
		reasoningTime: null,
		expandChunk: null,
		preview: null
	});

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
		this.showOutputDetails = {
			open: false,
			activeCell: null,
			activeTab: 'answer',
			message: null,
			reasoningContent: null,
			reasoningTime: null,
			expandChunk: null,
			preview: null
		};
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

	closeOutputDetails() {
		this.showOutputDetails = { ...this.showOutputDetails, open: false };
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
		this.showOutputDetails = {
			open: false,
			activeCell: null,
			activeTab: 'answer',
			message: null,
			reasoningContent: null,
			reasoningTime: null,
			expandChunk: null,
			preview: null
		};
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
	reasoningContentStreams: Record<string, Record<string, string>> = $state({});

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
	stream(rowID: string, colID: string, value: any, reasoning_content: string | null) {
		this.rows = this.rows?.map((row) => {
			if (row.ID === rowID) {
				return {
					...row,
					[colID]: {
						value: (row[colID]?.value ?? '') + value,
						reasoning_content: (row[colID]?.reasoning_content ?? '') + (reasoning_content ?? '')
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

	/** @param clientRowID If true, new row */
	async parseStream(
		tableState: TableState,
		reader: ReadableStreamDefaultReader<string>,
		clientRowID?: string
	) {
		let addedRow = false;
		let rowID = '';
		let buffer = '';
		// let renderCount = 0;
		// eslint-disable-next-line no-constant-condition
		while (true) {
			try {
				const { value, done } = await reader.read();
				if (done) break;

				buffer += value;
				const lines = buffer.split('\n'); //? Split by \n to handle collation
				buffer = lines.pop() || '';

				let parsedEvent: { data: GenTableStreamEvent } | undefined = undefined;
				for (const line of lines) {
					if (line === '') {
						if (parsedEvent) {
							if (parsedEvent.data.object === 'gen_table.completion.chunk') {
								if (parsedEvent.data.choices[0].finish_reason) {
									switch (parsedEvent.data.choices[0].finish_reason) {
										case 'error': {
											logger.error('TABLE_STREAMING_ERROR', parsedEvent.data);
											console.error('STREAMING_ERROR', parsedEvent.data);
											alert(
												`Error while streaming: ${parsedEvent.data.choices[0].message.content}`
											);
											break;
										}
									}
								} else {
									rowID = parsedEvent.data.row_id;

									if (clientRowID && !addedRow) {
										this.updateRow(clientRowID, {
											ID: parsedEvent.data.row_id,
											[parsedEvent.data.output_column_name]: {
												value: parsedEvent.data.choices[0].message.content ?? '',
												reasoning_content:
													parsedEvent.data.choices[0].message.reasoning_content ?? undefined
											}
										} as GenTableRow);

										const streamedCols = $state.snapshot(tableState.streamingRows[clientRowID]);
										tableState.delStreamingRows([clientRowID]);
										tableState.addStreamingRows({
											[parsedEvent.data.row_id]: streamedCols
										});
										addedRow = true;
									} else {
										this.stream(
											parsedEvent.data.row_id,
											parsedEvent.data.output_column_name,
											parsedEvent.data.choices[0].message.content ?? '',
											parsedEvent.data.choices[0].message.reasoning_content
										);
									}

									/** Stream output details dialog */
									if (
										tableState.showOutputDetails.activeCell?.rowID === rowID &&
										tableState.showOutputDetails.activeCell?.columnID ===
											parsedEvent.data.output_column_name
									) {
										tableState.showOutputDetails = {
											...tableState.showOutputDetails,
											message: {
												chunks: tableState.showOutputDetails.message?.chunks ?? [],
												error: tableState.showOutputDetails.message?.error ?? null,
												content:
													(tableState.showOutputDetails.message?.content ?? '') +
													(parsedEvent.data.choices[0].message.content ?? '')
											},
											reasoningContent:
												(tableState.showOutputDetails.reasoningContent ?? '') +
												(parsedEvent.data.choices[0].message.reasoning_content ?? '')
										};
									}

									if (parsedEvent.data.choices[0].message.reasoning_content) {
										const relevantCell = document.querySelector(
											`[data-row-id="${escapeHtmlText(rowID)}"][data-col-id="${escapeHtmlText(parsedEvent.data.output_column_name)}"] > [data-reasoning-text]`
										);
										if (relevantCell) {
											relevantCell.scrollTop = relevantCell.scrollHeight;
										}
									}
								}
							} else if (parsedEvent.data.object === 'gen_table.references') {
								/** Add references to rows */
								this.rows = this.rows?.map((row) => {
									if (!parsedEvent) return row;
									if (row.ID === parsedEvent.data.row_id) {
										return {
											...row,
											[parsedEvent.data.output_column_name]: {
												...row[parsedEvent.data.output_column_name],
												references: parsedEvent.data as unknown as ChatReferences
											}
										};
									}
									return row;
								});

								/** Add references to output details if active */
								if (
									tableState.showOutputDetails.activeCell?.rowID === rowID &&
									tableState.showOutputDetails.activeCell?.columnID ===
										parsedEvent.data.output_column_name
								) {
									tableState.showOutputDetails = {
										...tableState.showOutputDetails,
										message: {
											chunks: (parsedEvent.data as unknown as ChatReferences).chunks ?? [],
											error: tableState.showOutputDetails.message?.error ?? null,
											content: tableState.showOutputDetails.message?.content ?? ''
										}
									};
								}
							} else {
								console.warn('Unknown event data:', parsedEvent.data);
							}
						} else {
							console.warn('Unknown event object:', parsedEvent);
						}
					} else if (line.startsWith('data: ')) {
						if (line.slice(6) === '[DONE]') break;
						parsedEvent = { ...(parsedEvent ?? {}), data: JSON.parse(line.slice(6)) };
					} else if (line.startsWith('event: ')) {
						//@ts-expect-error missing type
						parsedEvent = { ...(parsedEvent ?? {}), event: line.slice(7) };
					}
				}
			} catch (err) {
				logger.error('CHAT_MESSAGE_ADDSTREAM', err);
				console.error(err);
				break;
			}
		}

		return { row_id: rowID };
	}
}

const tableRowsStateContextKey = 'tableRowsState';
export function setTableRowsState() {
	return setContext(tableRowsStateContextKey, new TableRowsState());
}

export function getTableRowsState() {
	return getContext<TableRowsState>(tableRowsStateContextKey);
}
