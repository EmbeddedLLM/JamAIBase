<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import debounce from 'lodash/debounce';
	import { PlusIcon, Trash2 } from '@lucide/svelte';
	import { browser } from '$app/environment';
	import { goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import { db } from '$lib/db';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import ActionTable from '$lib/components/tables/ActionTable.svelte';
	import { ColumnSettings, TablePagination, TableSorter } from '$lib/components/tables/(sub)';
	import OutputDetailsWrapper from '$lib/components/output-details/OutputDetailsWrapper.svelte';
	import { ActionsDropdown, GenerateButton } from '../../(components)';
	import { AddColumnDialog, DeleteDialogs } from '../../(dialogs)';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	let { data } = $props();
	let tableData: GenTable | undefined = $state();
	let tableRowsCount: number | undefined = $state();
	let tableError: { error: number; message: Awaited<typeof data.table>['message'] } | undefined =
		$state();
	let tableLoaded = $state(false);

	const resetTable = () => {
		if (!('then' in data.table)) return;
		Promise.all([
			data.table.then(async (tableRes) => {
				tableData = structuredClone(tableRes.data); // Client reorder column
				//TODO: Replace local tableData state with tableState.tableData
				tableState.tableData = tableData;
				if (tableRes.error) {
					tableError = { error: tableRes.error, message: tableRes.message };
				}

				if (tableData) tableState.setTemplateCols(tableData.cols);
				if (browser && tableData) {
					const savedColSizes = await db.action_table.get(page.params.table_id ?? '');
					if (savedColSizes) {
						tableState.colSizes = savedColSizes.columns;
					}
					tableState.setTemplateCols(tableData.cols);
				}
			}),
			data.tableRows.then((tableRowsRes) => {
				tableRowsState.rows = structuredClone(tableRowsRes.data?.rows); // Client reorder rows
				tableRowsState.loading = false;
				tableRowsCount = tableRowsRes.data?.total_rows;

				if (tableState.showOutputDetails.open) {
					const activeRow = tableRowsState.rows?.find(
						(row) => row.ID === tableState.showOutputDetails.activeCell?.rowID
					);
					const activeCell = activeRow?.[tableState.showOutputDetails.activeCell?.columnID ?? ''];
					if (activeRow && activeCell) {
						tableState.showOutputDetails = {
							...tableState.showOutputDetails,
							message: {
								content: activeCell.value,
								chunks: activeCell.references?.chunks ?? []
							},
							reasoningContent: activeCell.reasoning_content ?? null,
							reasoningTime: activeCell.reasoning_time ?? null
						};
					}
				}
			})
		]).then(() => (tableLoaded = true));
	};

	let searchQuery = $state('');
	let searchController: AbortController | null = null;
	let isLoadingSearch = $state(false);

	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = $state({
		type: 'input',
		showDialog: false
	});
	let isDeletingRow: string[] | null = $state(null);

	async function refetchTable(hideColumnSettings = true) {
		//? Don't refetch while streaming
		if (Object.keys(tableState.streamingRows).length === 0) {
			searchController?.abort('Duplicate');
			await invalidate('action-table:slug');
			isLoadingSearch = false;

			tableState.setSelectedRows([]);
			if (hideColumnSettings)
				tableState.setColumnSettings({ ...tableState.columnSettings, isOpen: false });
		}
	}

	async function handleSearchRows(q: string) {
		if (!tableData || !tableRowsState.rows) return;

		isLoadingSearch = true;

		if (searchQuery) {
			page.url.searchParams.set('q', searchQuery);
		} else {
			page.url.searchParams.delete('q');
		}
		goto(`?${page.url.searchParams}`, {
			replaceState: true,
			keepFocus: true,
			invalidate: []
		});

		searchController?.abort('Duplicate');
		searchController = new AbortController();

		try {
			const orderBy = page.url.searchParams.get('sort_by');
			const orderAsc = parseInt(page.url.searchParams.get('asc') ?? '0');

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/action/rows/list?${new URLSearchParams([
					['table_id', tableData.id],
					['limit', (100).toString()],
					['order_by', orderBy ?? 'ID'],
					['order_ascending', orderAsc === 1 ? 'true' : 'false'],
					['search_query', q]
				])}`,
				{
					signal: searchController.signal
				}
			);

			const responseBody = await response.json();
			if (response.ok) {
				tableRowsState.rows = responseBody.items;
			} else {
				logger.error('ACTIONTBL_TBL_SEARCHROWS', responseBody);
				console.error(responseBody);
				toast.error('Failed to search rows', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}
			isLoadingSearch = false;
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
				isLoadingSearch = false;
			}
		}
	}
	const debouncedSearchRows = debounce(handleSearchRows, 300);
	$effect(() => {
		(data.table, resetTable());
	});
</script>

<svelte:head>
	<title>{page.params.table_id} - Action Table</title>
</svelte:head>

<section
	id="action-table"
	class="relative flex h-screen max-h-screen min-h-0 min-w-0 flex-col overflow-hidden pt-0"
>
	<div
		data-testid="table-title-row"
		inert={tableState.columnSettings.isOpen}
		class="grid grid-cols-[minmax(0,max-content)_minmax(min-content,auto)] items-center gap-2 pb-1 pl-3 pr-2 pt-[1.5px] sm:pr-4 sm:pt-3"
	>
		<div class="flex items-center gap-2 text-sm sm:text-base">
			<Button
				variant="ghost"
				href="/project/{page.params.project_id}/action-table"
				title="Back to action tables"
				class="hidden aspect-square h-8 items-center justify-center p-0 sm:flex sm:h-9"
			>
				<ArrowBackIcon class="h-7" />
			</Button>
			<ActionTableIcon class="h-[18px] flex-[0_0_auto] text-[#475467]" />
			<span
				title={tableData
					? page.params.table_id
					: tableError?.error == 404
						? 'Not found'
						: 'Failed to load'}
				class="line-clamp-1 break-all font-medium text-[#344054]"
			>
				{#await data.table}
					{page.params.table_id}
				{:then { data }}
					{data ? data.id : tableError?.error === 404 ? 'Not found' : 'Failed to load'}
				{/await}
			</span>
		</div>

		<div style="grid-template-columns: auto min-content;" class="grid w-full place-items-end">
			{#if tableLoaded || (tableData && tableRowsState.rows)}
				<div
					title={tableState.selectedRows.length === 0 ? 'Select row to generate output' : undefined}
					style="grid-template-columns: minmax(0, 1fr) {tableState.selectedRows.length !== 0
						? 'minmax(0, 1fr)'
						: 'minmax(0, 0fr)'};"
					class="grid place-items-end items-center gap-1 {tableState.selectedRows.length !== 0 ||
					Object.keys(tableState.streamingRows).length !== 0
						? 'opacity-100'
						: 'opacity-80 [&>button>div]:bg-[#E4E7EC] [&_*]:!text-[#98A2B3] [&_button]:bg-[#E4E7EC]'} transition-[opacity,grid-template-columns]"
				>
					<GenerateButton
						inert={tableState.selectedRows.length === 0 ? true : undefined}
						tableType="action"
						{tableData}
						{refetchTable}
						class={tableState.selectedRows.length === 0
							? 'pointer-events-none z-[5] translate-x-1'
							: ''}
					/>

					<Button
						variant="action"
						inert={tableState.selectedRows.length === 0 ? true : undefined}
						title="Delete row(s)"
						onclick={() => (isDeletingRow = tableState.selectedRows)}
						class="flex aspect-square h-8 items-center gap-2 p-0 text-[#F04438] sm:h-9 md:aspect-auto md:px-3 {tableState
							.selectedRows.length !== 0
							? 'opacity-100'
							: 'pointer-events-none opacity-0'} transition-[opacity,background-color]"
					>
						<Trash2 class="h-4 w-4" />

						<span class="hidden md:block">Delete row(s)</span>
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
			{:else}
				<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[38px] sm:w-[100px]" />
			{/if}
		</div>
	</div>

	<div
		style="grid-template-columns: auto minmax(0, auto) min-content;"
		class="grid w-full place-items-end gap-1 pb-1.5 pl-3 pr-2 sm:pb-3 sm:pr-4"
	>
		{#if tableLoaded || (tableData && tableRowsState.rows)}
			<div class="flex gap-1 place-self-start">
				<SearchBar
					bind:searchQuery
					{isLoadingSearch}
					debouncedSearch={debouncedSearchRows}
					label="Search rows"
					class="w-[12rem] [&>input]:h-8 [&>input]:sm:h-9"
				/>

				<TableSorter {tableData} tableType="action" />
			</div>

			<div class="place-items-end">
				<Button
					variant="action"
					title="New column"
					onclick={async () => {
						tableState.addingCol = true;
						await tick();
						const table = document.querySelector('[data-testid=table-area]')?.firstChild;
						if (table) (table as HTMLElement).scrollLeft = 999999;
					}}
					class="flex aspect-square h-8 items-center gap-2 p-0 text-[#475467] sm:h-9 md:aspect-auto md:px-3"
				>
					<PlusIcon class="h-4 w-4" />

					<span class="hidden md:block">New column</span>
				</Button>
			</div>

			<ActionsDropdown tableType="action" {tableData} {refetchTable} />
		{:else}
			<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
			<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[36px] sm:w-[127px]" />
			<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
		{/if}
	</div>

	<ActionTable bind:tableData bind:tableError user={data.user} {refetchTable} />

	{#if !tableError}
		<TablePagination tableType="action" bind:tableData {tableRowsCount} {searchQuery} />
	{/if}

	<ColumnSettings {tableData} {refetchTable} tableType="action" />
</section>

<OutputDetailsWrapper bind:showOutputDetails={tableState.showOutputDetails} />
<AddColumnDialog bind:isAddingColumn {tableData} {refetchTable} tableType="action" />
<DeleteDialogs bind:isDeletingRow {refetchTable} tableType="action" />
