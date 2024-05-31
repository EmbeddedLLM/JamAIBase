<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import { showRightDock } from '$globalStore';
	import logger from '$lib/logger';
	import type {
		ActionTable,
		ActionTableCol,
		ActionTableRow,
		GenTableStreamEvent
	} from '$lib/types';

	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import ActionTables from './ActionTables.svelte';
	import { AddColumnDialog, AddRowDialog, AddTableDialog, DeleteDialogs } from './(dialogs)';
	import ColumnSettings from './ColumnSettings.svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import * as Pagination from '$lib/components/ui/pagination';
	import { Button } from '$lib/components/ui/button';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import DblArrowRightIcon from '$lib/icons/DblArrowRightIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import CodeIcon from '$lib/icons/CodeIcon.svelte';
	import ArrowFilledRightIcon from '$lib/icons/ArrowFilledRightIcon.svelte';
	import ColumnIcon from '$lib/icons/ColumnIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';
	import ArrowLeftIcon from '$lib/icons/ArrowLeftIcon.svelte';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let data;
	$: ({ table } = data);
	$: tableData = structuredClone(table?.tableData); // Client reorder column
	$: rows = structuredClone(table?.rows); // Client edit row
	let streamingRows: { [key: string]: boolean } = {};

	let rightDockButton: HTMLButtonElement;
	let showRightDockButton = false;

	//TODO: Change in prod
	let selected: string[] = [];
	let shiftOrigin: number | null = null;

	let isAddingTable = false;
	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isAddingRow = false;
	let isLoadingAddRow = false; //? Add row loading
	let isDeletingTable: string | null = null;
	let isDeletingColumn: string | null = null;
	let isDeletingRow: string[] | null = null;
	let isColumnSettingsOpen: { column: ActionTableCol | null; showMenu: boolean } = {
		column: null,
		showMenu: false
	};

	//? Reorder columns
	let isReorderLoading = false;
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = null;
	let draggingColumn: ActionTable['cols'][number] | null = null;
	let draggingColumnIndex: number | null = null;
	let hoveredColumnIndex: number | null = null;

	let isEditingCell: { rowID: string; columnID: string } | null = null;

	$: count = table?.total_rows ?? 0;
	$: perPage = 100;
	$: currentPage = parseInt($page.url.searchParams.get('page') ?? '1');

	$: resetOnUpdate(data.table?.tableData);
	function resetOnUpdate(tableData: ActionTable | undefined) {
		selected = [];
		isColumnSettingsOpen = { column: null, showMenu: false };
	}

	function refetchTable() {
		//? Don't refetch while streaming
		if (Object.keys(streamingRows).length === 0) {
			invalidate('action-table:slug');
		}
	}

	function mouseMoveListener(e: MouseEvent) {
		const tableArea = document.getElementById('action-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton.contains(el) ||
			(tableArea?.contains(el) && tableArea?.offsetWidth - (e.clientX - tableArea?.offsetLeft) < 75)
		) {
			showRightDockButton = true;
		} else {
			showRightDockButton = false;
		}
	}

	$: if (
		tableData &&
		draggingColumnIndex != null &&
		hoveredColumnIndex != null &&
		draggingColumnIndex != hoveredColumnIndex
	) {
		[tableData.cols[draggingColumnIndex], tableData.cols[hoveredColumnIndex]] = [
			tableData.cols[hoveredColumnIndex],
			tableData.cols[draggingColumnIndex]
		];

		draggingColumnIndex = hoveredColumnIndex;
	}

	async function handleSaveOrder() {
		if (!tableData) return;
		if (isReorderLoading) return;
		isReorderLoading = true;

		const response = await fetch(`/api/v1/gen_tables/action/columns/reorder`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: tableData.id,
				column_names: tableData.cols.flatMap(({ id }) =>
					id === 'ID' || id === 'Updated at' ? [] : id
				)
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_TBL_REORDER', responseBody);
			alert('Failed to reorder columns: ' + (responseBody.message || JSON.stringify(responseBody)));
			tableData = table?.tableData;
		} else {
			refetchTable();
		}

		isReorderLoading = false;
	}

	async function handleSaveEdit(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLTextAreaElement;
		}
	) {
		if (!tableData || !isEditingCell || !rows) return;
		const originalValue = rows.find((row) => row.ID === isEditingCell!.rowID)?.[
			isEditingCell.columnID
		];
		const editedValue = e.currentTarget.value;
		const cellToUpdate = isEditingCell;

		//? Optimistic update
		rows = rows.map((row) => {
			if (row.ID === cellToUpdate.rowID) {
				return {
					...row,
					[cellToUpdate.columnID]: { value: editedValue }
				};
			}
			return row;
		});

		const response = await fetch(`/api/v1/gen_tables/action/rows/update`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: tableData.id,
				row_id: cellToUpdate.rowID,
				data: {
					[cellToUpdate.columnID]: editedValue
				}
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_TBL_ROWEDIT', responseBody);
			alert('Failed to edit row: ' + (responseBody.message || JSON.stringify(responseBody)));

			//? Revert back to original value
			rows = rows.map((row) => {
				if (row.ID === cellToUpdate.rowID) {
					return {
						...row,
						[cellToUpdate.columnID]: {
							value: originalValue
						}
					};
				}
				return row;
			});
		} else {
			isEditingCell = null;
			refetchTable();
		}
	}

	//? Select row
	function handleSelectRow(
		e: CustomEvent<{ event: MouseEvent; value: boolean }>,
		row: ActionTableRow
	) {
		if (!rows) return;
		//? Select multiple rows with shift key
		const rowIndex = rows.findIndex(({ ID }) => ID === row.ID);
		if (e.detail.event.shiftKey && selected.length && shiftOrigin != null) {
			if (shiftOrigin < rowIndex) {
				selected = [
					...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
					...rows.slice(shiftOrigin, rowIndex + 1).map(({ ID }) => ID)
				];
			} else if (shiftOrigin > rowIndex) {
				selected = [
					...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
					...rows.slice(rowIndex, shiftOrigin + 1).map(({ ID }) => ID)
				];
			} else {
				selectOne();
			}
		} else {
			selectOne();
			shiftOrigin = rowIndex;
		}

		function selectOne() {
			if (selected.find((i) => i === row.ID)) {
				selected = selected.filter((i) => i !== row.ID);
			} else {
				selected = [...selected, row.ID];
			}
		}
	}

	async function handleRegenRow(toRegenRowIds: string[]) {
		if (!rows) return;

		streamingRows = {
			...streamingRows,
			...toRegenRowIds.reduce((acc, curr) => ({ ...acc, [curr]: true }), {})
		};

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: rows!.find((row) => row.ID === toRegenRowId)!
		}));
		rows = rows?.map((row) => {
			if (toRegenRowIds.includes(row.ID)) {
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
										value: tableData?.cols.find((col) => col.id == key)?.gen_config
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

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_ROW_REGEN', responseBody);
			alert('Failed to regenerate row: ' + (responseBody.message || JSON.stringify(responseBody)));

			//? Revert back to original value
			rows = rows.map((row) => {
				const originalValue = originalValues.find((i) => i.id === row.ID);
				if (toRegenRowIds.includes(row.ID) && originalValue) {
					return originalValue.value;
				}
				return row;
			});
		} else {
			//Delete all data except for inputs
			rows = rows.map((row) => {
				if (toRegenRowIds.includes(row.ID)) {
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
											value: tableData?.cols.find((col) => col.id == key)?.gen_config
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

			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error('ACTIONTBL_ROW_REGENSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							console.log(parsedValue);

							if (parsedValue.object == 'gen_table.completion.chunk') {
								//* Add chunk to active row'
								//@ts-expect-error wtf
								const rowMatchIndex = rows.findIndex((row) => row.ID == parsedValue.row_id);
								if (rowMatchIndex != undefined && rowMatchIndex != -1) {
									//@ts-expect-error wtf
									const [start, end] = [
										rows?.slice(0, rowMatchIndex),
										rows?.slice(rowMatchIndex + 1)
									];
									rows = [
										...(start ?? []),
										{
											...rows![rowMatchIndex],
											[parsedValue.output_column_name]: {
												value:
													(rows![rowMatchIndex][parsedValue.output_column_name]?.value ?? '') +
													(parsedValue.choices[0].message.content ?? '')
											}
										},
										...(end ?? [])
									];
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					// logger.error('ACTIONTBL_ROW_REGENSTREAM', err);
					console.error(err);

					//? Below necessary for retry
					for (const toRegenRowId of toRegenRowIds) {
						delete streamingRows[toRegenRowId];
					}
					streamingRows = streamingRows;

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		for (const toRegenRowId of toRegenRowIds) {
			delete streamingRows[toRegenRowId];
		}
		streamingRows = streamingRows;

		refetchTable();
	}

	async function addRowFunction(data: any) {
		isLoadingAddRow = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				data: [data],
				stream: true
			})
		});

		isAddingRow = false;
		isLoadingAddRow = false;

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_ROW_ADD', responseBody);
			alert('Failed to add row: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			let rowId = '';
			let addedRow = false;
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error('ACTIONTBL_ROW_ADDSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							if (parsedValue.object == 'gen_table.completion.chunk') {
								rowId = parsedValue.row_id;
								streamingRows = {
									...streamingRows,
									[parsedValue.row_id]: true
								};

								//* Add chunk to active row
								if (!addedRow) {
									rows = [
										{
											...(Object.fromEntries(
												Object.entries(data).map(([key, value]) => [
													key,
													{ value: value as string }
												])
											) as any),
											ID: parsedValue.row_id,
											'Updated at': new Date().toISOString(),
											[parsedValue.output_column_name]: {
												value: parsedValue.choices[0].message.content ?? ''
											}
										},
										...(rows ?? [])
									];
									addedRow = true;
								} else {
									const rowMatchIndex = rows?.findIndex((row) => row.ID == parsedValue.row_id);

									if (rowMatchIndex != undefined && rowMatchIndex != -1) {
										const [start, end] = [
											rows?.slice(0, rowMatchIndex),
											rows?.slice(rowMatchIndex + 1)
										];
										rows = [
											...(start ?? []),
											{
												...rows![rowMatchIndex],
												[parsedValue.output_column_name]: {
													value:
														(rows![rowMatchIndex][parsedValue.output_column_name]?.value ?? '') +
														(parsedValue.choices[0].message.content ?? '')
												}
											},
											...(end ?? [])
										];
									}
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					logger.error('ACTIONTBL_ROW_ADDSTREAM', err);
					console.error(err);
					break;
				}
			}

			delete streamingRows[rowId];
			streamingRows = streamingRows;

			refetchTable();
		}
	}

	function keyboardNavigate(e: KeyboardEvent) {
		if (!rows) return;
		const isCtrl = window.navigator.userAgent.indexOf('Mac') != -1 ? e.metaKey : e.ctrlKey;
		const activeElement = document.activeElement as HTMLElement;
		const isInputActive = activeElement.tagName == 'INPUT' || activeElement.tagName == 'TEXTAREA';
		if (isCtrl && e.key === 'a' && !isInputActive) {
			e.preventDefault();
			selected = [
				...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
				...rows.map(({ ID }) => ID)
			];
		}
	}
</script>

<svelte:window on:mousemove={mouseMoveListener} />
<svelte:document on:keydown={keyboardNavigate} />

<svelte:head>
	<title>{$page.params.table_id} - Action Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto) ${$showRightDock ? '20rem' : '0rem'};`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="action-table"
		class="relative flex flex-col pt-0 pb-12 min-h-0 max-h-screen min-w-0 overflow-hidden"
	>
		<BreadcrumbsBar />

		<div
			inert={isColumnSettingsOpen.showMenu}
			class="flex items-center justify-between px-4 py-3 gap-2"
		>
			<div class="flex items-center gap-2">
				<ActionTableIcon class="flex-[0_0_auto] h-6 w-6 text-secondary -translate-y-0.5" />
				<span class="font-medium line-clamp-1">
					{tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
				</span>
			</div>

			<div class="flex items-center gap-1.5">
				{#if tableData && rows}
					<div class="flex items-center gap-4">
						<Button
							on:click={() => (isAddingRow = true)}
							class="px-2.5 py-0 h-9 text-text bg-black/[0.04] data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1]"
						>
							<AddIcon class="w-3 h-3 mr-2" />
							Add row
						</Button>
					</div>

					<!-- <Button
						on:click={() => alert('open get code')}
						variant="ghost"
						class="flex gap-2 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
					>
						<CodeIcon class="h-5 w-5" />
						Get Code
					</Button> -->

					<DropdownMenu.Root>
						<DropdownMenu.Trigger asChild let:builder>
							<Button
								builders={[builder]}
								variant="ghost"
								class="flex gap-3 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
							>
								Actions
								<ArrowFilledRightIcon class="h-2.5 w-2.5" />
							</Button>
						</DropdownMenu.Trigger>
						<DropdownMenu.Content alignOffset={-40} transitionConfig={{ x: 5, y: -5 }}>
							<DropdownMenu.Group>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
										column
									</span>
								</DropdownMenu.Item>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#A67835] data-dark:text-[#DA9F47]">output</span>
										column
									</span>
								</DropdownMenu.Item>
							</DropdownMenu.Group>
							<!-- <DropdownMenu.Separator />
							<DropdownMenu.Group>
								<DropdownMenu.Item>
									<ImportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
									Import rows
								</DropdownMenu.Item>
								<DropdownMenu.Item>
									<ExportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
									Export rows
								</DropdownMenu.Item>
							</DropdownMenu.Group> -->
							{#if selected.length}
								<DropdownMenu.Separator />
								<DropdownMenu.Group>
									{#if selected.length}
										<DropdownMenu.Item
											on:click={() => {
												handleRegenRow(selected.filter((i) => !streamingRows[i]));
												selected = [];
											}}
											class="pl-[5px]"
										>
											<RegenerateIcon class="h-5 w-5 mr-[5px]" />
											Regenerate row
										</DropdownMenu.Item>
									{/if}
									<DropdownMenu.Item on:click={() => (isDeletingRow = selected)}>
										<Trash2 class="h-3.5 w-3.5 mr-2 mb-[2px]" />
										Delete row(s)
									</DropdownMenu.Item>
								</DropdownMenu.Group>
							{/if}
						</DropdownMenu.Content>
					</DropdownMenu.Root>
				{/if}
			</div>
		</div>

		{#if tableData && rows}
			<div inert={isColumnSettingsOpen.showMenu} class="grow flex flex-col w-full min-h-0">
				<div
					role="grid"
					style="grid-template-rows: 46px repeat({rows.length}, min-content);"
					class="grow relative grid px-4 overflow-auto"
				>
					<div
						role="row"
						style="grid-template-columns: 60px repeat({tableData.cols.length}, minmax(320px, 1fr));"
						class="sticky top-0 z-20 h-min grid text-sm border border-[#E5E5E5] data-dark:border-[#333] rounded-lg bg-white data-dark:bg-[#42464E] overflow-hidden"
					>
						<div role="columnheader" class="flex items-center px-4 py-3">
							<Checkbox
								on:checkedChange={() => {
									if (rows) {
										return rows.every((row) => selected.includes(row.ID))
											? (selected = selected.filter((i) => !rows?.some(({ ID }) => ID === i)))
											: (selected = [
													...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
													...rows.map(({ ID }) => ID)
												]);
									} else return false;
								}}
								checked={rows.every((row) => selected.includes(row.ID))}
								class="h-5 w-5"
							/>
						</div>
						{#each tableData.cols as column, index (column.id)}
							{@const colType = !column.gen_config ? 'input' : 'output'}
							<!-- svelte-ignore a11y-interactive-supports-focus -->
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<div
								role="columnheader"
								title={column.id}
								on:click={() => {
									if (column.id !== 'ID' && column.id !== 'Updated at') {
										isColumnSettingsOpen = { column, showMenu: true };
									}
								}}
								on:dragover={(e) => {
									if (column.id !== 'ID' && column.id !== 'Updated at') {
										e.preventDefault();
										hoveredColumnIndex = index;
									}
								}}
								class="flex items-center gap-2 pl-4 pr-5 py-2 cursor-default {isColumnSettingsOpen
									.column?.id == column.id && isColumnSettingsOpen.showMenu
									? 'bg-[#30A8FF33]'
									: ''} {draggingColumn?.id == column.id ? 'opacity-0' : ''}"
							>
								{#if column.id !== 'ID' && column.id !== 'Updated at'}
									<button
										disabled={isReorderLoading}
										on:click|stopPropagation
										on:dragstart={(e) => {
											//@ts-ignore
											let rect = e.target.getBoundingClientRect();
											dragMouseCoords = {
												x: e.clientX,
												y: e.clientY,
												startX: e.clientX - rect.left,
												startY: e.clientY - rect.top,
												//@ts-ignore
												width: e.target.parentElement.offsetWidth
											};
											draggingColumn = column;
											draggingColumnIndex = index;
										}}
										on:drag={(e) => {
											if (e.clientX === 0 && e.clientY === 0) return;
											//@ts-ignore
											dragMouseCoords = { ...dragMouseCoords, x: e.clientX, y: e.clientY };
										}}
										on:dragend={() => {
											dragMouseCoords = null;
											draggingColumn = null;
											draggingColumnIndex = null;
											hoveredColumnIndex = null;
											handleSaveOrder();
										}}
										draggable={true}
										class="cursor-grab disabled:cursor-not-allowed"
									>
										<GripVertical size={18} />
									</button>

									<span
										style="background-color: {colType === 'input'
											? '#CFE8FF'
											: '#FFE3CF'}; color: {colType === 'input' ? '#3A73B6' : '#B6843A'};"
										class="w-min px-1 py-0.5 capitalize text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
									>
										{colType}
									</span>
								{/if}

								<span class="font-medium text-[#666] data-dark:text-white line-clamp-1">
									{column.id}
								</span>

								{#if column.id !== 'ID' && column.id !== 'Updated at'}
									<DropdownMenu.Root>
										<DropdownMenu.Trigger asChild let:builder>
											<Button
												on:click={(e) => e.stopPropagation()}
												builders={[builder]}
												variant="ghost"
												title="Column actions"
												class="ml-auto p-0 h-7 w-7 aspect-square rounded-full"
											>
												<MoreVertIcon class="h-[18px] w-[18px]" />
											</Button>
										</DropdownMenu.Trigger>
										<DropdownMenu.Content alignOffset={-65} transitionConfig={{ x: 5, y: -5 }}>
											<DropdownMenu.Group>
												<DropdownMenu.Item
													on:click={() => (isColumnSettingsOpen = { column, showMenu: true })}
												>
													<TuneIcon class="h-4 w-4 mr-2 mb-[1px]" />
													<span>Open settings</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
											<DropdownMenu.Separator />
											<DropdownMenu.Group>
												<DropdownMenu.Item on:click={() => (isDeletingColumn = column.id)}>
													<Trash2 class="h-4 w-4 mr-2 mb-[2px]" />
													<span>Delete column</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								{/if}
							</div>
						{/each}
					</div>

					<!-- Bandaid fix for no scrolling when no rows -->
					<div
						style="grid-template-columns: 60px repeat({tableData.cols.length}, minmax(320px, 1fr));"
						class="z-0 grid place-items-start h-min max-h-[150px] text-sm pointer-events-none invisible"
					></div>

					{#each rows as row (row.ID)}
						<div
							role="row"
							style="grid-template-columns: 60px repeat({tableData.cols
								.length}, minmax(320px, 1fr));"
							class="relative z-0 grid place-items-start h-min max-h-[150px] text-sm transition-colors {streamingRows[
								row.ID
							]
								? 'border border-blink-secondary'
								: 'border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-[#E5E5E5] data-dark:border-[#333]'}"
						>
							<div role="gridcell" class="px-4 py-3">
								<Checkbox
									on:checkedChange={(e) => handleSelectRow(e, row)}
									checked={!!selected.find((i) => i === row.ID)}
									class="h-5 w-5"
								/>
							</div>
							{#each tableData.cols as column}
								{@const editMode =
									isEditingCell &&
									isEditingCell.rowID === row.ID &&
									isEditingCell.columnID === column.id}
								<!-- svelte-ignore a11y-interactive-supports-focus -->
								<div
									role="gridcell"
									tabindex="0"
									on:dblclick={() => {
										if (column.id === 'ID' || column.id === 'Updated at') return;
										if (!streamingRows[row.ID]) {
											isEditingCell = { rowID: row.ID, columnID: column.id };
										}
									}}
									on:keydown={(e) => {
										if (column.id === 'ID' || column.id === 'Updated at') return;
										if (!editMode && e.key == 'Enter' && !streamingRows[row.ID]) {
											isEditingCell = { rowID: row.ID, columnID: column.id };
										}
									}}
									class="{editMode
										? 'p-0 bg-black/5 data-dark:bg-white/5'
										: 'px-5 py-3 overflow-auto whitespace-pre-line'} h-full max-h-[150px] w-full break-words {isColumnSettingsOpen
										.column?.id == column.id && isColumnSettingsOpen.showMenu
										? 'bg-[#30A8FF17]'
										: ''} hover:bg-black/5 data-dark:hover:bg-white/5 {streamingRows[row.ID] &&
									column.id !== 'ID' &&
									column.id !== 'Updated at' &&
									column.gen_config
										? 'response-cursor'
										: ''}"
								>
									{#if editMode}
										<!-- svelte-ignore a11y-autofocus -->
										<textarea
											autofocus
											value={row[column.id].value}
											on:keydown={(e) => {
												if (e.key === 'Enter' && !e.shiftKey) {
													e.preventDefault();

													handleSaveEdit(e);
												} else if (e.key === 'Escape') {
													isEditingCell = null;
												}
											}}
											on:blur={() => (isEditingCell = null)}
											class="min-h-[150px] h-full w-full px-5 py-3 bg-transparent outline outline-seconartext-secondary data-dark:outline-[#5b7ee5] resize-none"
										/>
									{:else if column.id === 'ID'}
										{row[column.id]}
									{:else if column.id === 'Updated at'}
										{new Date(row[column.id]).toLocaleString()}
									{:else}
										{row[column.id]?.value === undefined ? '' : row[column.id].value}
									{/if}
								</div>
							{/each}
						</div>
					{/each}
				</div>
			</div>

			<div
				inert={isColumnSettingsOpen.showMenu}
				class="flex items-center justify-between px-4 py-3 min-h-[55px] border-t border-[#E5E5E5] data-dark:border-[#333]"
			>
				<div class="flex items-end gap-6">
					<span class="text-sm font-medium text-[#666] data-dark:text-white">
						Showing {count == 0 ? 0 : perPage * currentPage - perPage + 1}-{perPage * currentPage >
						count
							? count
							: perPage * currentPage} of {count} rows
					</span>

					{#if selected.length}
						<span class="text-xs font-medium text-[#666] data-dark:text-white">
							Selected {selected.length} rows
						</span>
					{/if}
				</div>

				{#if count > 0}
					<Pagination.Root page={currentPage} {count} {perPage} let:pages class="w-[unset] mx-0">
						<Pagination.Content>
							<Pagination.Item>
								<Pagination.PrevButton>
									<ArrowLeftIcon class="h-4 w-4" />
								</Pagination.PrevButton>
							</Pagination.Item>
							{#each pages as page (page.key)}
								{#if page.type === 'ellipsis'}
									<Pagination.Item>
										<Pagination.Ellipsis />
									</Pagination.Item>
								{:else}
									<Pagination.Item>
										<Pagination.Link asChild isActive={currentPage === page.value} {page}>
											<a
												href="?page={page.value}"
												class="inline-flex items-center justify-center rounded-md text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
											>
												{page.value}
											</a>
										</Pagination.Link>
									</Pagination.Item>
								{/if}
							{/each}
							<Pagination.Item>
								<Pagination.NextButton>
									<ArrowRightIcon class="h-4 w-4" />
								</Pagination.NextButton>
							</Pagination.Item>
						</Pagination.Content>
					</Pagination.Root>
				{/if}
			</div>
		{:else if table && table.error == 404}
			<div class="flex items-center justify-center h-full">
				<p class="font-medium text-xl">Table not found</p>
			</div>
		{:else if table && table.error}
			<div class="flex flex-col items-center justify-center gap-2 self-center h-full max-w-[50%]">
				<p class="font-medium text-xl">{table.error} Failed to load table</p>
				<p class="text-sm text-[#999]">{table.message}</p>
			</div>
		{:else}
			<div class="flex items-center justify-center h-full">
				<LoadingSpinner class="h-5 w-5 text-secondary" />
			</div>
		{/if}

		<ColumnSettings bind:isColumnSettingsOpen bind:isDeletingColumn />
	</section>

	<section
		class="relative z-[1] flex flex-col gap-2 min-h-0 bg-white data-dark:bg-[#303338] border-l border-[#DDD] data-dark:border-[#2A2A2A]"
	>
		<!-- Close right dock button -->
		<div
			class="absolute top-1/2 -translate-y-1/2 -left-16 flex items-center justify-end h-[80%] w-16 overflow-hidden pointer-events-none"
		>
			<button
				bind:this={rightDockButton}
				title="Show/hide action table history"
				on:click={() => ($showRightDock = !$showRightDock)}
				on:focusin={() => (showRightDockButton = true)}
				on:focusout={() => (showRightDockButton = false)}
				class={`p-1 bg-white data-dark:bg-[#303338] border border-[#DDD] data-dark:border-[#2A2A2A] rounded-l-xl ${
					showRightDockButton ? 'translate-x-0' : 'translate-x-11'
				} transition-transform duration-300 pointer-events-auto`}
			>
				<DblArrowRightIcon class={`w-8 h-8 ${!$showRightDock && 'rotate-180'}`} />
			</button>
		</div>

		<Button
			disabled={!$showRightDock}
			variant="outline"
			title="New table"
			on:click={() => (isAddingTable = true)}
			class="flex items-center gap-3 m-4 mx-6 mt-10 p-4 text-secondary hover:text-secondary text-center border-2 border-secondary bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-lg whitespace-nowrap overflow-hidden"
		>
			<AddIcon class="w-3 h-3" />
			New table
		</Button>

		<ActionTables bind:isDeletingTable />
	</section>
</div>

<!-- Dragged item -->
{#if dragMouseCoords && draggingColumn}
	{@const colType = !draggingColumn.gen_config /* || Object.keys(column.gen_config).length === 0 */
		? 'input'
		: 'output'}
	<div
		style="top: {dragMouseCoords.y - dragMouseCoords.startY - 15}px; left: {dragMouseCoords.x -
			dragMouseCoords.startX -
			15}px; width: {dragMouseCoords.width}px;"
		class="absolute z-[9999] flex items-center gap-2 pl-4 pr-5 py-2 bg-white data-dark:bg-[#42464E] pointer-events-none"
	>
		<button>
			<GripVertical size={18} />
		</button>

		<span
			style="background-color: {colType === 'input' ? '#CFE8FF' : '#FFE3CF'}; color: {colType ===
			'input'
				? '#3A73B6'
				: '#B6843A'};"
			class="w-min px-1 py-0.5 capitalize text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
		>
			{colType}
		</span>

		<span class="font-medium text-sm text-[#666] data-dark:text-white line-clamp-1">
			{draggingColumn.id}
		</span>

		{#if draggingColumn.id !== 'ID' && draggingColumn.id !== 'Updated at'}
			<Button
				variant="ghost"
				title="Column settings"
				class="ml-auto p-0 h-7 w-7 aspect-square rounded-full"
			>
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		{/if}
	</div>
{/if}

<AddTableDialog bind:isAddingTable />
<AddColumnDialog bind:isAddingColumn />
<AddRowDialog bind:isAddingRow bind:isLoadingAddRow {addRowFunction} />
<DeleteDialogs bind:isDeletingTable bind:isDeletingColumn bind:isDeletingRow />
