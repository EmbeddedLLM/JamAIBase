<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import { genTableRows } from '$lib/components/tables/tablesStore';
	import { isValidUri } from '$lib/utils';
	import { chatTableStaticCols } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol, GenTableRow, UserRead } from '$lib/types';

	import {
		ColumnDropdown,
		DeleteFileDialog,
		FileColumnView,
		FileSelect,
		FileThumbsFetch,
		NewRow
	} from '$lib/components/tables/(sub)';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import Portal from '$lib/components/Portal.svelte';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';

	export let userData: UserRead | undefined;
	export let table: Promise<
		| {
				error: number;
				message: any;
				data?: undefined;
		  }
		| {
				data: GenTable;
				error?: undefined;
				message?: undefined;
		  }
	>;
	export let tableData: GenTable | undefined;
	export let tableError: { error: number; message: Awaited<typeof table>['message'] } | undefined;
	export let selectedRows: string[];
	export let streamingRows: Record<string, string[]>;
	export let isColumnSettingsOpen: { column: any; showMenu: boolean };
	export let isDeletingColumn: string | null;
	export let readonly = false;
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;

	let rowThumbs: { [rowID: string]: { [colID: string]: { value: string; url: string } } } = {};
	let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null = null;
	let uploadController: AbortController | undefined = undefined;

	//? Expanding ID and Updated at columns
	let focusedCol: string | null = null;

	//? Column header click handler
	let isRenamingColumn: string | null = null;
	let dblClickTimer: NodeJS.Timeout | null = null;
	function handleColumnHeaderClick(column: GenTableCol) {
		if (!tableData) return;
		if (isRenamingColumn) return;

		if (dblClickTimer) {
			clearTimeout(dblClickTimer);
			dblClickTimer = null;
			if (!readonly && !chatTableStaticCols.includes(column.id)) {
				isRenamingColumn = column.id;
			}
		} else {
			dblClickTimer = setTimeout(() => {
				if (column.id !== 'ID' && column.id !== 'Updated at' && column.gen_config) {
					isColumnSettingsOpen = { column, showMenu: true };
				}
				dblClickTimer = null;
			}, 200);
		}
	}

	async function handleSaveColumnTitle(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLInputElement;
		}
	) {
		if (!tableData || !$genTableRows) return;
		if (!isRenamingColumn) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/columns/rename`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				column_map: {
					[isRenamingColumn]: e.currentTarget.value
				}
			})
		});

		if (response.ok) {
			refetchTable();
			tableData = {
				...tableData,
				cols: tableData.cols.map((col) =>
					col.id === isRenamingColumn ? { ...col, id: e.currentTarget.value } : col
				)
			};
			isRenamingColumn = null;
		} else {
			const responseBody = await response.json();
			logger.error('CHATTBL_COLUMN_RENAME', responseBody);
			toast.error('Failed to rename column', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}

	//? Reorder columns
	let isReorderLoading = false;
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = null;
	let draggingColumn: GenTable['cols'][number] | null = null;
	let draggingColumnIndex: number | null = null;
	let hoveredColumnIndex: number | null = null;

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
		if (!tableData || !$genTableRows) return;
		if (isReorderLoading) return;
		isReorderLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/columns/reorder`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: tableData.id,
				column_names: tableData.cols.flatMap(({ id }) =>
					id === 'ID' || id === 'Updated at' ? [] : id
				)
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('CHATTBL_TBL_REORDER', responseBody);
			toast.error('Failed to reorder columns', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			tableData = (await table)?.data;
		} else {
			refetchTable();
		}

		isReorderLoading = false;
	}

	let isEditingCell: { rowID: string; columnID: string } | null = null;
	async function handleSaveEdit(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLTextAreaElement;
		}
	) {
		if (!tableData || !$genTableRows) return;
		if (!isEditingCell) return;

		const editedValue = e.currentTarget.value;
		const cellToUpdate = isEditingCell;

		await saveEditCell(cellToUpdate, editedValue);
	}

	async function saveEditCell(
		cellToUpdate: { rowID: string; columnID: string },
		editedValue: string
	) {
		if (!tableData || !$genTableRows) return;

		//? Optimistic update
		const originalValue = $genTableRows.find((row) => row.ID === cellToUpdate!.rowID)?.[
			cellToUpdate.columnID
		];
		genTableRows.setCell(cellToUpdate, editedValue);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/rows/update`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
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
			logger.error('CHATTBL_TBL_ROWEDIT', responseBody);
			toast.error('Failed to edit row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			genTableRows.setCell(cellToUpdate, originalValue);
		} else {
			isEditingCell = null;
			refetchTable();
		}
	}

	let shiftOrigin: number | null = null;
	//? Select row
	function handleSelectRow(
		e: CustomEvent<{ event: MouseEvent; value: boolean }>,
		row: GenTableRow
	) {
		if (!tableData || !$genTableRows) return;
		//? Select multiple rows with shift key
		const rowIndex = $genTableRows.findIndex(({ ID }) => ID === row.ID);
		if (e.detail.event.shiftKey && selectedRows.length && shiftOrigin != null) {
			if (shiftOrigin < rowIndex) {
				selectedRows = [
					...selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
					...$genTableRows.slice(shiftOrigin, rowIndex + 1).map(({ ID }) => ID)
				];
			} else if (shiftOrigin > rowIndex) {
				selectedRows = [
					...selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
					...$genTableRows.slice(rowIndex, shiftOrigin + 1).map(({ ID }) => ID)
				];
			} else {
				selectOne();
			}
		} else {
			selectOne();
			shiftOrigin = rowIndex;
		}

		function selectOne() {
			if (selectedRows.find((i) => i === row.ID)) {
				selectedRows = selectedRows.filter((i) => i !== row.ID);
			} else {
				selectedRows = [...selectedRows, row.ID];
			}
		}
	}

	function keyboardNavigate(e: KeyboardEvent) {
		if (!tableData || !$genTableRows) return;
		const isCtrl = window.navigator.userAgent.indexOf('Mac') != -1 ? e.metaKey : e.ctrlKey;
		const activeElement = document.activeElement as HTMLElement;
		const isInputActive = activeElement.tagName == 'INPUT' || activeElement.tagName == 'TEXTAREA';
		if (isCtrl && e.key === 'a' && !isInputActive) {
			e.preventDefault();

			if (Object.keys(streamingRows).length !== 0) return;

			selectedRows = [
				...selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
				...$genTableRows.map(({ ID }) => ID)
			];
		}

		if (e.key === 'Escape') {
			isEditingCell = null;
		}
	}

	onDestroy(() => {
		$genTableRows = undefined;
	});
</script>

<svelte:document
	on:mousedown={(e) => {
		const editingCell = document.querySelector('[data-editing="true"]');
		//@ts-ignore
		if (e.target && editingCell && !editingCell.contains(e.target)) {
			isEditingCell = null;
		}
	}}
	on:keydown={keyboardNavigate}
/>

{#if tableData}
	<div
		data-testid="table-area"
		inert={isColumnSettingsOpen.showMenu}
		class="grow flex flex-col w-full min-h-0"
	>
		<div
			on:scroll={(e) => {
				//? Used to prevent elements showing through the padding between side nav and table header
				//FIXME: Use transform for performance
				const el = document.getElementById('checkbox-bg-obscure');
				if (el) {
					el.style.left = `-${e.currentTarget.scrollLeft > 20 ? 20 : e.currentTarget.scrollLeft}px`;
				}
			}}
			role="grid"
			style="grid-template-rows: 36px {$genTableRows
				? `repeat(${$genTableRows.length + (!readonly ? 1 : 0)}, min-content)`
				: 'minmax(0, 1fr)'};"
			class="grow relative grid px-2 overflow-auto"
		>
			<div
				role="row"
				style="grid-template-columns: 45px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
				'Updated at'
					? '320px'
					: '130px'} {tableData.cols.length - 2 !== 0
					? `repeat(${tableData.cols.length - 2}, minmax(320px, 1fr))`
					: ''};"
				class="sticky top-0 z-20 h-[36px] grid text-xs sm:text-sm border border-[#E4E7EC] data-dark:border-[#333] rounded-lg bg-white data-dark:bg-[#42464E] transition-[grid-template-columns] duration-200"
			>
				<!-- Obscure padding between header and side nav bar -->
				<div
					class="absolute -z-0 -top-[1px] -left-[9px] h-[37px] w-4 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
				/>

				<div
					role="columnheader"
					class="sticky left-0 z-0 flex items-center justify-center px-2 bg-white data-dark:bg-[#42464E] border-r border-[#E4E7EC] data-dark:border-[#333] rounded-l-lg"
				>
					<div
						id="checkbox-bg-obscure"
						class="absolute -z-10 -top-[1px] -left-0 h-[36px] w-full bg-white data-dark:bg-[#42464E] border-l border-t border-b border-[#E4E7EC] data-dark:border-[#333] rounded-l-lg"
					/>

					{#if !readonly}
						<Checkbox
							on:checkedChange={() => {
								if ($genTableRows) {
									return $genTableRows.every((row) => selectedRows.includes(row.ID))
										? (selectedRows = selectedRows.filter(
												(i) => !$genTableRows?.some(({ ID }) => ID === i)
											))
										: (selectedRows = [
												...selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
												...$genTableRows.map(({ ID }) => ID)
											]);
								} else return false;
							}}
							checked={($genTableRows ?? []).every((row) => selectedRows.includes(row.ID))}
							class="h-4 sm:h-[18px] w-4 sm:w-[18px] [&>svg]:h-3 sm:[&>svg]:h-3.5 [&>svg]:w-3 sm:[&>svg]:w-3.5 [&>svg]:translate-x-[1px]"
						/>
					{/if}
				</div>

				{#each tableData.cols as column, index (column.id)}
					{@const colType = !column.gen_config ? 'input' : 'output'}
					{@const isCustomCol = column.id !== 'ID' && column.id !== 'Updated at'}
					<!-- svelte-ignore a11y-interactive-supports-focus -->
					<!-- svelte-ignore a11y-click-events-have-key-events -->
					<div
						role="columnheader"
						title={column.id}
						on:click={() => handleColumnHeaderClick(column)}
						on:dragover={(e) => {
							if (isCustomCol) {
								e.preventDefault();
								hoveredColumnIndex = index;
							}
						}}
						class="flex items-center gap-1 {isCustomCol && !readonly
							? 'px-1'
							: 'pl-2 pr-1'} cursor-default [&:not(:last-child)]:border-r border-[#E4E7EC] data-dark:border-[#333] {isColumnSettingsOpen
							.column?.id == column.id && isColumnSettingsOpen.showMenu
							? 'bg-[#30A8FF33]'
							: ''} {draggingColumn?.id == column.id ? 'opacity-0' : ''}"
					>
						{#if isCustomCol && !readonly}
							<button
								title="Drag to reorder columns"
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
						{/if}

						{#if column.id !== 'ID' && column.id !== 'Updated at'}
							<span
								style="background-color: {colType === 'input'
									? '#E9EDFA'
									: '#FFEAD5'}; color: {colType === 'input' ? '#6686E7' : '#FD853A'};"
								class="w-min mr-1 px-0.5 py-1 text-xxs sm:text-xs whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
							>
								<span class="capitalize font-medium px-1">
									{colType}
								</span>
								<span
									class="bg-white w-min px-1 font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
								>
									{column.dtype}
								</span>

								{#if column.gen_config?.object === 'gen_config.llm' && column.gen_config.multi_turn}
									<hr class="ml-1 h-3 border-l border-[#FD853A]" />
									<div class="relative h-4 w-[18px]">
										<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
									</div>
								{/if}
							</span>
						{/if}

						{#if isRenamingColumn === column.id}
							<!-- svelte-ignore a11y-autofocus -->
							<input
								type="text"
								id="column-id-edit"
								autofocus
								value={column.id}
								on:keydown={(e) => {
									if (e.key === 'Enter') {
										e.preventDefault();

										handleSaveColumnTitle(e);
									} else if (e.key === 'Escape') {
										isRenamingColumn = null;
									}
								}}
								on:blur={() => setTimeout(() => (isRenamingColumn = null), 100)}
								class="w-full bg-transparent border-0 outline outline-1 outline-[#4169e1] data-dark:outline-[#5b7ee5] rounded-[2px]"
							/>
						{:else}
							<span
								class="w-full font-medium {column.id === 'ID' || column.id === 'Updated at'
									? 'text-[#98A2B3]'
									: 'text-[#666] data-dark:text-white'} line-clamp-1 break-all"
							>
								{column.id}
							</span>
						{/if}

						{#if (!chatTableStaticCols.includes(column.id) || colType === 'output') && !readonly}
							<ColumnDropdown
								tableType="chat"
								bind:isColumnSettingsOpen
								bind:isRenamingColumn
								bind:isDeletingColumn
								bind:selectedRows
								bind:streamingRows
								{column}
								{tableData}
								{refetchTable}
								{readonly}
							/>
						{/if}
					</div>
				{/each}
			</div>

			{#if $genTableRows}
				{#if !readonly}
					<NewRow tableType="chat" bind:streamingRows {tableData} {focusedCol} {refetchTable} />
				{/if}

				<!-- Bandaid fix for no scrolling when no rows -->
				<div
					style="grid-template-columns: 45px 120px 130px repeat({tableData.cols.length -
						2}, minmax(320px, 1fr));"
					class="z-0 grid place-items-start h-0 pointer-events-none invisible"
				/>

				{#each $genTableRows as row}
					<div
						data-streaming={!!streamingRows[row.ID] || undefined}
						role="row"
						style="grid-template-columns: 45px {focusedCol === 'ID'
							? '320px'
							: '120px'} {focusedCol === 'Updated at' ? '320px' : '130px'} {tableData.cols.length -
							2 !==
						0
							? `repeat(${tableData.cols.length - 2}, minmax(320px, 1fr))`
							: ''};"
						class="relative z-0 grid place-items-start h-min max-h-[100px] sm:max-h-[150px] text-xs sm:text-sm transition-[border-color,grid-template-columns] duration-200 border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-[#E4E7EC] data-dark:border-[#333] group"
					>
						<div
							role="gridcell"
							class="sticky z-[1] left-0 flex justify-center px-2 py-1.5 sm:py-2 h-full w-full border-r border-[#E4E7EC] data-dark:border-[#333]"
						>
							<!-- Streaming row colored part -->
							{#if streamingRows[row.ID]}
								<div
									class="absolute -z-[1] -top-[1px] -left-[9px] h-[calc(100%_+_2px)] w-1.5 bg-[#F2839F]"
								/>
							{/if}

							<div
								class="absolute -z-10 top-0 -left-4 h-full w-[calc(100%_+_16px)] {streamingRows[
									row.ID
								]
									? 'bg-[#FDEFF4]'
									: 'bg-[#FAFBFC] data-dark:bg-[#1E2024] group-hover:bg-[#ECEDEE]'}"
							/>
							{#if !readonly}
								<Checkbox
									on:checkedChange={(e) => handleSelectRow(e, row)}
									checked={!!selectedRows.find((i) => i === row.ID)}
									class="mt-[1px] h-4 sm:h-[18px] w-4 sm:w-[18px] [&>svg]:h-3 sm:[&>svg]:h-3.5 [&>svg]:w-3 sm:[&>svg]:w-3.5 [&>svg]:translate-x-[1px]"
								/>
							{/if}
						</div>
						{#each tableData.cols as column}
							{@const editMode =
								isEditingCell &&
								isEditingCell.rowID === row.ID &&
								isEditingCell.columnID === column.id}
							{@const isValidFileUri = isValidUri(row[column.id]?.value)}
							<!-- svelte-ignore a11y-interactive-supports-focus -->
							<div
								data-editing={editMode ? true : undefined}
								role="gridcell"
								tabindex="0"
								on:focusin={() => (focusedCol = column.id)}
								on:focusout={() => (focusedCol = null)}
								on:mousedown={(e) => {
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (column.dtype === 'file' && row[column.id]?.value && isValidFileUri) return;
									if (uploadController) return;
									if (streamingRows[row.ID] || isEditingCell) return;

									if (e.detail > 1) {
										e.preventDefault();
									}
								}}
								on:dblclick={() => {
									if (readonly) return;
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (column.dtype === 'file' && row[column.id]?.value && isValidFileUri) return;
									if (uploadController) return;

									if (!streamingRows[row.ID]) {
										isEditingCell = { rowID: row.ID, columnID: column.id };
									}
								}}
								on:keydown={(e) => {
									if (readonly) return;
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (column.dtype === 'file' && row[column.id]?.value && isValidFileUri) return;
									if (uploadController) return;

									if (!editMode && e.key == 'Enter' && !streamingRows[row.ID]) {
										isEditingCell = { rowID: row.ID, columnID: column.id };
									}
								}}
								style={isColumnSettingsOpen.column?.id == column.id && isColumnSettingsOpen.showMenu
									? 'background-color: #30A8FF17;'
									: ''}
								class="flex flex-col justify-start gap-1 {editMode
									? 'p-0 bg-black/5 data-dark:bg-white/5'
									: 'p-2 overflow-auto whitespace-pre-line'} h-full max-h-[99px] sm:max-h-[149px] w-full break-words {streamingRows[
									row.ID
								]
									? 'bg-[#FDEFF4]'
									: 'group-hover:bg-[#ECEDEE] data-dark:group-hover:bg-white/5'} [&:not(:last-child)]:border-r border-[#E4E7EC] data-dark:border-[#333]"
							>
								{#if streamingRows[row.ID]?.includes(column.id) && !editMode && column.id !== 'ID' && column.id !== 'Updated at' && column.gen_config}
									<RowStreamIndicator />
								{/if}

								{#if editMode}
									{#if column.dtype === 'file'}
										<FileSelect
											tableType="chat"
											controller={uploadController}
											cellToUpdate={{ rowID: row.ID, columnID: column.id }}
											{saveEditCell}
										/>
									{:else}
										<!-- svelte-ignore a11y-autofocus -->
										<textarea
											autofocus
											value={row[column.id].value}
											on:keydown={(e) => {
												if (e.key === 'Enter' && !e.shiftKey) {
													e.preventDefault();

													handleSaveEdit(e);
												}
											}}
											class="min-h-[100px] sm:min-h-[150px] h-full w-full p-2 bg-transparent outline outline-secondary resize-none"
										/>
									{/if}
								{:else if column.dtype === 'file'}
									<FileColumnView
										tableType="chat"
										rowID={row.ID}
										columnID={column.id}
										fileUri={row[column.id]?.value}
										fileUrl={rowThumbs[row.ID]?.[column.id]?.url}
										bind:isDeletingFile
									/>
								{:else}
									<span
										class="h-min {column.id === 'ID' || column.id === 'Updated at'
											? 'text-[#667085] line-clamp-1 break-all'
											: 'text-text'} whitespace-pre-line"
									>
										{#if column.id === 'ID'}
											{row[column.id]}
										{:else if column.id === 'Updated at'}
											{new Date(row[column.id]).toISOString()}
										{:else}
											{row[column.id]?.value === undefined ? null : row[column.id]?.value}
										{/if}
									</span>
								{/if}
							</div>
						{/each}
					</div>
				{/each}
			{:else}
				<div class="flex items-center">
					<LoadingSpinner class="sticky left-1/2 h-5 w-5 text-secondary" />
				</div>
			{/if}
		</div>
	</div>
{:else if tableError?.error == 404}
	{#if tableError.message?.org_id && userData?.member_of.find((org) => org.organization_id === tableError.message?.org_id)}
		{@const projectOrg = userData?.member_of.find(
			(org) => org.organization_id === tableError.message?.org_id
		)}
		<FoundProjectOrgSwitcher {projectOrg} message="Table not found" />
	{:else}
		<div class="flex items-center justify-center h-full">
			<p class="font-medium text-xl">Table not found</p>
		</div>
	{/if}
{:else if tableError?.error}
	<div class="flex flex-col items-center justify-center gap-2 self-center h-full max-w-[50%]">
		<p class="font-medium text-xl">{tableError.error} Failed to load table</p>
		<p class="text-sm text-[#999]">{JSON.stringify(tableError.message)}</p>
	</div>
{:else}
	<div class="flex items-center justify-center h-full">
		<LoadingSpinner class="h-5 w-5 text-secondary" />
	</div>
{/if}

{#if dragMouseCoords && draggingColumn}
	{@const colType = !draggingColumn.gen_config /* || Object.keys(column.gen_config).length === 0 */
		? 'input'
		: 'output'}
	<Portal>
		<div
			data-testid="dragged-column"
			inert
			style="top: {dragMouseCoords.y - dragMouseCoords.startY - 15}px; left: {dragMouseCoords.x -
				dragMouseCoords.startX -
				15}px; width: {dragMouseCoords.width}px;"
			class="fixed z-[9999] flex items-center gap-1 px-1 h-[36px] bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] pointer-events-none"
		>
			<button>
				<GripVertical size={18} />
			</button>

			<span
				style="background-color: {colType === 'input' ? '#E9EDFA' : '#FFEAD5'}; color: {colType ===
				'input'
					? '#6686E7'
					: '#FD853A'};"
				class="w-min mr-1 px-0.5 py-1 text-xxs sm:text-xs whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
			>
				<span class="capitalize font-medium px-1">
					{colType}
				</span>
				<span
					class="bg-white w-min px-1 font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
				>
					{draggingColumn.dtype}
				</span>
			</span>

			<span class="font-medium text-xs sm:text-sm text-[#666] data-dark:text-white line-clamp-1">
				{draggingColumn.id}
			</span>

			<Button
				variant="ghost"
				title="Column settings"
				class="ml-auto p-0 h-7 w-7 aspect-square rounded"
			>
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		</div>
	</Portal>
{/if}

<FileThumbsFetch {tableData} {streamingRows} bind:rowThumbs />
<DeleteFileDialog
	bind:isDeletingFile
	deleteCb={() => {
		if (isDeletingFile) {
			saveEditCell(isDeletingFile, '');
			delete rowThumbs[isDeletingFile?.rowID][isDeletingFile?.columnID];
			isDeletingFile = null;
		}
	}}
/>
