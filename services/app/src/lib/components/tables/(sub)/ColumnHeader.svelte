<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import { page } from '$app/stores';
	import { genTableRows, tableState } from '$lib/components/tables/tablesStore';
	import { db } from '$lib/db';
	import { cn } from '$lib/utils';
	import { tableStaticCols } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { ColumnDropdown } from '$lib/components/tables/(sub)';
	import Portal from '$lib/components/Portal.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable;
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	export let readonly: boolean;

	//? Column header click handler
	let dblClickTimer: ReturnType<typeof setTimeout> | null = null;
	function handleColumnHeaderClick(column: GenTableCol) {
		if (!tableData) return;
		if ($tableState.renamingCol) return;

		if (dblClickTimer) {
			clearTimeout(dblClickTimer);
			dblClickTimer = null;
			if (!readonly && !tableStaticCols[tableType].includes(column.id)) {
				tableState.setRenamingCol(column.id);
			}
		} else {
			dblClickTimer = setTimeout(() => {
				if (column.id !== 'ID' && column.id !== 'Updated at' && column.gen_config) {
					tableState.setColumnSettings({ isOpen: true, column });
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
		if (!$tableState.renamingCol) return;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/columns/rename`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': $page.params.project_id
				},
				body: JSON.stringify({
					table_id: $page.params.table_id,
					column_map: {
						[$tableState.renamingCol]: e.currentTarget.value
					}
				})
			}
		);

		if (response.ok) {
			refetchTable();
			tableData = {
				...tableData,
				cols: tableData.cols.map((col) =>
					col.id === $tableState.renamingCol ? { ...col, id: e.currentTarget.value } : col
				)
			};
			tableState.setRenamingCol(null);
		} else {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_RENAME`), responseBody);
			toast.error('Failed to rename column', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}

	function startColResize(e: MouseEvent, columnID: string) {
		if (tableData) {
			tableData.cols
				.filter((col) => col.id !== 'ID' && col.id !== 'Updated at')
				.forEach((col) => {
					const colEl = document.querySelector(`[role="columnheader"][title="${col.id}"]`);
					if (colEl) tableState.setColSize(col.id, colEl.getBoundingClientRect().width);
				});

			let rect = (e.target as HTMLElement).getBoundingClientRect();
			const isLastCol = tableData.cols.at(-1)?.id === columnID;
			tableState.setResizingCol({
				columnID,
				diffX: e.clientX - rect.left - rect.width / 2 - (isLastCol ? 0 : 1)
			});

			handleColResize(e);
		}
	}

	function handleColResize(e: MouseEvent) {
		if ($tableState.resizingCol) {
			const clientX = e.clientX;
			const tableGrid = document
				.querySelector('[data-testid="table-area"]')
				?.querySelector('[role="grid"]');

			if (tableGrid) {
				const tableOffsetLeft =
					tableGrid.getBoundingClientRect().left +
					parseFloat(getComputedStyle(tableGrid).paddingLeft);
				const pageScrollX = tableGrid.scrollLeft;
				const column = document.querySelector(
					`[role="columnheader"][title="${$tableState.resizingCol.columnID}"]`
				);

				const columnLeftX =
					(column?.getBoundingClientRect().left ?? 0) + pageScrollX - tableOffsetLeft;
				const columnRightX =
					clientX - $tableState.resizingCol.diffX + pageScrollX - tableOffsetLeft;
				const columnWidth = columnRightX - columnLeftX;

				tableState.setColSize(
					$tableState.resizingCol.columnID,
					columnWidth < 100 ? 100 : columnWidth
				);
				tableState.setTemplateCols(tableData.cols);
			}
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

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/columns/reorder`,
			{
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
			}
		);

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_TBL_REORDER`), responseBody);
			toast.error('Failed to reorder columns', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			tableData = (await $page.data.table)?.data;
		} else {
			refetchTable();
		}

		isReorderLoading = false;
	}
</script>

<svelte:document
	on:mousemove={handleColResize}
	on:mouseup={() => {
		if ($tableState.resizingCol) {
			db[`${tableType}_table`].put({
				id: tableData.id,
				columns: $tableState.colSizes
			});
			$tableState.resizingCol = null;
		}
	}}
/>

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
		class={cn(
			'relative [&>*]:z-[-5] flex items-center gap-1 [&:not(:last-child)]:border-r border-[#E4E7EC] data-dark:border-[#333] cursor-default',
			isCustomCol && !readonly ? 'px-1' : 'pl-2 pr-1',
			$tableState.columnSettings.column?.id == column.id &&
				$tableState.columnSettings.isOpen &&
				'bg-[#30A8FF33]',
			draggingColumn?.id == column.id && 'opacity-0'
		)}
	>
		{#if isCustomCol}
			<button
				tabindex={-1}
				aria-label="Resize column"
				on:click|stopPropagation
				on:dblclick|stopPropagation={() => {
					$tableState = { ...$tableState, colSizes: {} };
					tableState.setTemplateCols(tableData.cols);
					db[`${tableType}_table`].put({
						id: tableData.id,
						columns: {}
					});
				}}
				on:mousedown={(e) => startColResize(e, column.id)}
				class="absolute !z-10 -right-[3px] top-0 bottom-0 w-[6px] hover:bg-[#F2F4F7] transition-colors cursor-ew-resize"
			></button>
		{/if}

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
				class="!z-0 cursor-grab disabled:cursor-not-allowed"
			>
				<GripVertical size={18} />
			</button>
		{/if}

		{#if column.id !== 'ID' && column.id !== 'Updated at'}
			{#if !$tableState.colSizes[column.id] || $tableState.colSizes[column.id] >= 150}
				<span
					style="background-color: {colType === 'input'
						? '#E9EDFA'
						: '#FFEAD5'}; color: {colType === 'input' ? '#6686E7' : '#FD853A'};"
					class="w-min mr-1 px-0.5 py-1 text-xxs sm:text-xs whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
				>
					<span class="capitalize font-medium px-1">
						{colType}
					</span>
					{#if !$tableState.colSizes[column.id] || $tableState.colSizes[column.id] >= 220}
						<span
							class="bg-white w-min px-1 font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
						>
							{column.dtype}
						</span>
					{/if}

					{#if column.gen_config?.object === 'gen_config.llm' && column.gen_config.multi_turn}
						<hr class="ml-1 h-3 border-l border-[#FD853A]" />
						<div class="relative h-4 w-[18px]">
							<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
						</div>
					{/if}
				</span>
			{/if}
		{/if}

		{#if $tableState.renamingCol === column.id}
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
						tableState.setRenamingCol(null);
					}
				}}
				on:blur={() => setTimeout(() => tableState.setRenamingCol(null), 100)}
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

		{#if (!tableStaticCols[tableType].includes(column.id) || colType === 'output') && !readonly}
			<ColumnDropdown {tableType} {column} {tableData} {refetchTable} {readonly} />
		{/if}
	</div>
{/each}

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

			{#if !$tableState.colSizes[draggingColumn.id] || $tableState.colSizes[draggingColumn.id] >= 150}
				<span
					style="background-color: {colType === 'input'
						? '#E9EDFA'
						: '#FFEAD5'}; color: {colType === 'input' ? '#6686E7' : '#FD853A'};"
					class="w-min mr-1 px-0.5 py-1 text-xxs sm:text-xs whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
				>
					<span class="capitalize font-medium px-1">
						{colType}
					</span>
					{#if !$tableState.colSizes[draggingColumn.id] || $tableState.colSizes[draggingColumn.id] >= 220}
						<span
							class="bg-white w-min px-1 font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
						>
							{draggingColumn.dtype}
						</span>
					{/if}

					{#if draggingColumn.gen_config?.object === 'gen_config.llm' && draggingColumn.gen_config.multi_turn}
						<hr class="ml-1 h-3 border-l border-[#FD853A]" />
						<div class="relative h-4 w-[18px]">
							<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
						</div>
					{/if}
				</span>
			{/if}

			<span class="font-medium text-xs sm:text-sm text-[#666] data-dark:text-white line-clamp-1">
				{draggingColumn.id}
			</span>

			<Button variant="ghost" title="Column settings" class="ml-auto p-0 h-7 w-7 aspect-square">
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		</div>
	</Portal>
{/if}
