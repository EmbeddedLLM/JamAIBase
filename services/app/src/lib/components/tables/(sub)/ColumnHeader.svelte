<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import toUpper from 'lodash/toUpper';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import { db } from '$lib/db';
	import { cn } from '$lib/utils';
	import { columnIDPattern, tableStaticCols } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import PlaceholderNewCol from './PlaceholderNewCol.svelte';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { ColumnDropdown } from '$lib/components/tables/(sub)';
	import Portal from '$lib/components/Portal.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
		readonly: boolean;
	}

	let { tableType, tableData = $bindable(), refetchTable, readonly }: Props = $props();

	//? Column header click handler
	let dblClickTimer: ReturnType<typeof setTimeout> | null = null;
	function handleColumnHeaderClick(column: GenTableCol) {
		if (!tableData) return;
		if (tableState.renamingCol) return;

		if (dblClickTimer) {
			clearTimeout(dblClickTimer);
			dblClickTimer = null;
			if (!readonly && !tableStaticCols[tableType].includes(column.id)) {
				tableState.setRenamingCol(column.id);
				tick().then(() => document.getElementById('column-id-edit')?.focus());
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
		if (!tableData || !tableRowsState.rows) return;
		if (!tableState.renamingCol) return;

		if (!columnIDPattern.test(e.currentTarget.value))
			return toast.error(
				'Column name must have at least 1 character and up to 46 characters, start with an alphabet or number, and end with an alphabet or number or these symbols: .?!()-. Characters in the middle can include space and these symbols: .?!@#$%^&*_()-.',
				{ id: 'column-name-invalid' }
			);

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/columns/rename`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
				},
				body: JSON.stringify({
					table_id: page.params.table_id,
					column_map: {
						[tableState.renamingCol]: e.currentTarget.value
					}
				})
			}
		);

		if (response.ok) {
			refetchTable();
			tableData = {
				...tableData,
				cols: tableData.cols.map((col) =>
					col.id === tableState.renamingCol ? { ...col, id: e.currentTarget.value } : col
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
		if (tableState.resizingCol) {
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
					`[role="columnheader"][title="${tableState.resizingCol.columnID}"]`
				);

				const columnLeftX =
					(column?.getBoundingClientRect().left ?? 0) + pageScrollX - tableOffsetLeft;
				const columnRightX = clientX - tableState.resizingCol.diffX + pageScrollX - tableOffsetLeft;
				const columnWidth = columnRightX - columnLeftX;

				tableState.setColSize(
					tableState.resizingCol.columnID,
					columnWidth < 100 ? 100 : columnWidth
				);
				tableState.setTemplateCols(tableData.cols);
			}
		}
	}

	//? Reorder columns
	let isReorderLoading = $state(false);
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = $state(null);
	let draggingColumn: GenTable['cols'][number] | null = $state(null);
	let draggingColumnIndex: number | null = $state(null);
	let hoveredColumnIndex: number | null = $state(null);

	$effect(() => {
		if (
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
	});

	async function handleSaveOrder() {
		if (!tableData || !tableRowsState.rows) return;
		if (isReorderLoading) return;
		isReorderLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/columns/reorder`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
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
			tableData = (await page.data.table)?.data;
		} else {
			refetchTable();
		}

		isReorderLoading = false;
	}
</script>

<svelte:document
	onmousemove={handleColResize}
	onmouseup={() => {
		if (tableState.resizingCol) {
			db[`${tableType}_table`].put({
				id: tableData.id,
				columns: $state.snapshot(tableState.colSizes)
			});
			tableState.resizingCol = null;
		}
	}}
/>

{#each tableData.cols as column, index (column.id)}
	{@const colType = !column.gen_config ? 'input' : 'output'}
	{@const isCustomCol = column.id !== 'ID' && column.id !== 'Updated at'}
	<!-- svelte-ignore a11y_interactive_supports_focus -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		role="columnheader"
		title={column.id}
		onclick={() => handleColumnHeaderClick(column)}
		ondragover={(e) => {
			if (isCustomCol) {
				e.preventDefault();
				hoveredColumnIndex = index;
			}
		}}
		class={cn(
			'relative flex cursor-default items-center gap-1 border-[#E4E7EC] data-dark:border-[#333] [&:not(:last-child)]:border-r [&>*]:z-[-5]',
			isCustomCol && !readonly ? 'px-1' : 'pl-2 pr-1',
			tableState.columnSettings.column?.id == column.id &&
				tableState.columnSettings.isOpen &&
				'bg-[#30A8FF33]',
			draggingColumn?.id == column.id && 'opacity-0',
			tableState.renamingCol && 'pointer-events-none'
		)}
	>
		{#if isCustomCol}
			<button
				tabindex={-1}
				aria-label="Resize column"
				onclick={(e) => e.stopPropagation()}
				ondblclick={(e) => {
					e.stopPropagation();
					tableState.colSizes = {};
					tableState.setTemplateCols(tableData.cols);
					db[`${tableType}_table`].put({
						id: tableData.id,
						columns: {}
					});
				}}
				onmousedown={(e) => startColResize(e, column.id)}
				class="absolute -right-[3px] bottom-0 top-0 !z-10 w-[6px] cursor-ew-resize transition-colors hover:bg-[#F2F4F7]"
			></button>
		{/if}

		{#if isCustomCol && !readonly}
			<button
				title="Drag to reorder columns"
				disabled={isReorderLoading}
				onclick={(e) => e.stopPropagation()}
				ondragstart={(e) => {
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
				ondrag={(e) => {
					if (e.clientX === 0 && e.clientY === 0) return;
					//@ts-ignore
					dragMouseCoords = { ...dragMouseCoords, x: e.clientX, y: e.clientY };
				}}
				ondragend={() => {
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
			{#if !tableState.colSizes[column.id] || tableState.colSizes[column.id] >= 150}
				<span
					style="background-color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
					class:pr-1={column.gen_config?.object !== 'gen_config.llm' ||
						!column.gen_config.multi_turn}
					class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-lg px-0.5 py-1 text-xxs text-white sm:text-xs"
				>
					<span class="px-1 font-medium capitalize">
						{colType}
					</span>
					{#if !tableState.colSizes[column.id] || tableState.colSizes[column.id] >= 220}
						<span
							style="color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
							class="w-min select-none whitespace-nowrap rounded-md bg-white px-1 font-medium"
						>
							{column.dtype}
						</span>
					{/if}

					{#if column.gen_config?.object === 'gen_config.llm' && column.gen_config.multi_turn}
						<hr class="ml-1 h-3 border-l border-white" />
						<div class="relative h-4 w-[18px]">
							<MultiturnChatIcon class="absolute h-[18px] -translate-y-px text-white" />
						</div>
					{/if}
				</span>
			{/if}
		{/if}

		{#if tableState.renamingCol === column.id}
			<!-- svelte-ignore a11y_autofocus -->
			<input
				type="text"
				id="column-id-edit"
				value={column.id}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();

						handleSaveColumnTitle(e);
					} else if (e.key === 'Escape') {
						tableState.setRenamingCol(null);
					}
				}}
				onblur={() => setTimeout(() => tableState.setRenamingCol(null), 100)}
				class="pointer-events-auto w-full rounded-[2px] border-0 bg-transparent outline outline-1 outline-[#4169e1] data-dark:outline-[#5b7ee5]"
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

{#if tableState.addingCol}
	<PlaceholderNewCol {tableType} {tableData} {refetchTable} />
{/if}

<Portal>
	{#if dragMouseCoords && draggingColumn}
		{@const colType =
			!draggingColumn.gen_config /* || Object.keys(column.gen_config).length === 0 */
				? 'input'
				: 'output'}
		<div
			data-testid="dragged-column"
			inert
			style="top: {dragMouseCoords.y - dragMouseCoords.startY - 15}px; left: {dragMouseCoords.x -
				dragMouseCoords.startX -
				15}px; width: {dragMouseCoords.width}px;"
			class="pointer-events-none fixed z-[9999] flex h-[36px] items-center gap-1 border border-[#E4E7EC] bg-white px-1 data-dark:border-[#333] data-dark:bg-[#42464E]"
		>
			<button>
				<GripVertical size={18} />
			</button>

			{#if !tableState.colSizes[draggingColumn.id] || tableState.colSizes[draggingColumn.id] >= 150}
				<span
					style="background-color: {colType === 'input'
						? '#E9EDFA'
						: '#FFEAD5'}; color: {colType === 'input' ? '#6686E7' : '#FD853A'};"
					class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-[0.1875rem] px-0.5 py-1 text-xxs sm:text-xs"
				>
					<span class="px-1 font-medium capitalize">
						{colType}
					</span>
					{#if !tableState.colSizes[draggingColumn.id] || tableState.colSizes[draggingColumn.id] >= 220}
						<span
							class="w-min select-none whitespace-nowrap rounded-[0.1875rem] bg-white px-1 font-medium"
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

			<span class="line-clamp-1 text-xs font-medium text-[#666] data-dark:text-white sm:text-sm">
				{draggingColumn.id}
			</span>

			<Button variant="ghost" title="Column settings" class="ml-auto aspect-square h-7 w-7 p-0">
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		</div>
	{/if}
</Portal>
