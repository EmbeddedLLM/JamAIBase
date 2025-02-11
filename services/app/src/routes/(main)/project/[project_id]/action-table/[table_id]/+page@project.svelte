<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { browser } from '$app/environment';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { genTableRows, tableState } from '$lib/components/tables/tablesStore';
	import { db } from '$lib/db';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import ActionTable from '$lib/components/tables/ActionTable.svelte';
	import { ColumnSettings, TablePagination } from '$lib/components/tables/(sub)';
	import { ActionsDropdown, GenerateButton } from '../../(components)';
	import { AddColumnDialog, DeleteDialogs } from '../../(dialogs)';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';

	export let data;
	$: ({ table, tableRows, userData } = data);
	let tableData: GenTable | undefined;
	let tableRowsCount: number | undefined;
	let tableError: { error: number; message: Awaited<typeof table>['message'] } | undefined;
	let tableLoaded = false;

	$: table, resetTable();
	const resetTable = () => {
		if (!('then' in table)) return;
		Promise.all([
			table.then(async (tableRes) => {
				tableData = structuredClone(tableRes.data); // Client reorder column
				if (tableRes.error) {
					tableError = { error: tableRes.error, message: tableRes.message };
				}

				if (tableData) tableState.setTemplateCols(tableData.cols);
				if (browser && tableData) {
					const savedColSizes = await db.action_table.get($page.params.table_id);
					if (savedColSizes) {
						$tableState.colSizes = savedColSizes.columns;
					}
					tableState.setTemplateCols(tableData.cols);
				}
			}),
			tableRows.then((tableRowsRes) => {
				$genTableRows = structuredClone(tableRowsRes.data?.rows); // Client reorder rows
				tableRowsCount = tableRowsRes.data?.total_rows;
			})
		]).then(() => (tableLoaded = true));
	};

	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isDeletingRow: string[] | null = null;

	async function refetchTable(hideColumnSettings = true) {
		//? Don't refetch while streaming
		if (Object.keys($tableState.streamingRows).length === 0) {
			if (searchQuery) {
				await handleSearchRows(searchQuery);
			} else {
				searchController?.abort('Duplicate');
				await invalidate('action-table:slug');
				isLoadingSearch = false;
			}

			tableState.setSelectedRows([]);
			if (hideColumnSettings)
				tableState.setColumnSettings({ ...$tableState.columnSettings, isOpen: false });
		}
	}

	async function handleSearchRows(q: string) {
		if (!tableData || !$genTableRows) return;

		isLoadingSearch = true;

		if (!searchQuery) return refetchTable();

		searchController?.abort('Duplicate');
		searchController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/${tableData.id}/rows?${new URLSearchParams({
					limit: (100).toString(),
					search_query: q
				})}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
				}
			);

			const responseBody = await response.json();
			if (response.ok) {
				$genTableRows = responseBody.items;
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
</script>

<svelte:head>
	<title>{$page.params.table_id} - Action Table</title>
</svelte:head>

<section
	id="action-table"
	class="relative flex flex-col pt-0 min-h-0 h-screen max-h-screen min-w-0 overflow-hidden"
>
	<div
		data-testid="table-title-row"
		inert={$tableState.columnSettings.isOpen}
		class="grid grid-cols-[minmax(0,max-content)_minmax(min-content,auto)] items-center pl-4 pr-2 sm:pr-4 pt-[1.5px] sm:pt-3 pb-1.5 sm:pb-3 gap-2"
	>
		<div class="flex items-center gap-2 text-sm sm:text-base">
			<a
				href="/project/{$page.params.project_id}/action-table"
				class="[all:unset] !hidden sm:!block"
			>
				<Button
					variant="ghost"
					title="Back to action tables"
					class="flex items-center justify-center p-0 h-8 sm:h-9 aspect-square"
				>
					<ArrowBackIcon class="h-7" />
				</Button>
			</a>
			<ActionTableIcon class="flex-[0_0_auto] h-[18px] text-[#475467]" />
			<span
				title={tableData
					? $page.params.table_id
					: tableError?.error == 404
						? 'Not found'
						: 'Failed to load'}
				class="font-medium text-[#344054] line-clamp-1 break-all"
			>
				{#await table}
					{$page.params.table_id}
				{:then { data }}
					{data ? data.id : tableError?.error === 404 ? 'Not found' : 'Failed to load'}
				{/await}
			</span>
		</div>

		<div
			style="grid-template-columns: minmax(min-content,auto) auto min-content;"
			class="grid place-items-end gap-1 w-full"
		>
			{#if tableLoaded || (tableData && $genTableRows)}
				<SearchBar
					bind:searchQuery
					{isLoadingSearch}
					debouncedSearch={debouncedSearchRows}
					label="Search rows"
					class="{searchQuery ? 'w-[12rem]' : 'w-[6.5rem]'} place-self-start"
				/>

				<div
					title={$tableState.selectedRows.length === 0
						? 'Select row to generate output'
						: undefined}
					style="grid-template-columns: minmax(0, 1fr) {$tableState.selectedRows.length !== 0
						? 'minmax(0, 1fr)'
						: 'minmax(0, 0fr)'};"
					class="grid place-items-end items-center gap-1 {$tableState.selectedRows.length !== 0 ||
					Object.keys($tableState.streamingRows).length !== 0
						? 'opacity-100'
						: 'opacity-80 [&_*]:!text-[#98A2B3] [&_button]:bg-[#E4E7EC] [&>button>div]:bg-[#E4E7EC]'} transition-[opacity,grid-template-columns]"
				>
					<GenerateButton
						inert={$tableState.selectedRows.length === 0 ? true : undefined}
						tableType="action"
						{tableData}
						{refetchTable}
						class={$tableState.selectedRows.length === 0
							? 'z-[5] translate-x-1 pointer-events-none'
							: ''}
					/>

					<Button
						inert={$tableState.selectedRows.length === 0 ? true : undefined}
						title="Delete row(s)"
						on:click={() => (isDeletingRow = $tableState.selectedRows)}
						class="flex items-center gap-2 p-0 md:px-3 h-8 sm:h-9 text-[#F04438] bg-[#F2F4F7] hover:bg-[#E4E7EC] focus-visible:bg-[#E4E7EC] active:bg-[#E4E7EC] aspect-square md:aspect-auto {$tableState
							.selectedRows.length !== 0
							? 'opacity-100'
							: 'opacity-0 pointer-events-none'} transition-opacity"
					>
						<Trash_2 class="h-4 w-4" />

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

				<ActionsDropdown tableType="action" bind:isAddingColumn {tableData} {refetchTable} />
			{:else}
				<Skeleton class="h-[32px] sm:h-[36px] w-[32px] sm:w-[36px] rounded-full place-self-start" />
				<Skeleton class="h-[32px] sm:h-[38px] w-[32px] sm:w-[100px] rounded-full" />
				<Skeleton class="h-[32px] sm:h-[38px] w-[32px] sm:w-[38px] rounded-full" />
			{/if}
		</div>
	</div>

	<ActionTable bind:userData bind:tableData bind:tableError {refetchTable} />

	{#if !tableError}
		<TablePagination tableType="action" bind:tableData {tableRowsCount} {searchQuery} />
	{/if}

	<ColumnSettings {tableData} {refetchTable} tableType="action" />
</section>

<AddColumnDialog bind:isAddingColumn {tableData} {refetchTable} tableType="action" />
<DeleteDialogs bind:isDeletingRow {refetchTable} tableType="action" />
