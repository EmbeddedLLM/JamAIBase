<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import { genTableRows } from '../../tablesStore';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import ActionTable from './ActionTable.svelte';
	import { ActionsDropdown, ColumnSettings, TablePagination } from '../../(components)';
	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import { AddColumnDialog, AddRowDialog, DeleteDialogs } from '../../(dialogs)';
	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import CodeIcon from '$lib/icons/CodeIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	export let data;
	$: ({ table, userData } = data);
	let tableData: GenTable | undefined;
	$: if (table?.tableData || table?.rows) resetTable();
	const resetTable = () => {
		tableData = structuredClone(table?.tableData); // Client reorder column
		$genTableRows = structuredClone(table?.rows); // Client reorder rows
	};

	let streamingRows: Record<string, boolean> = {};

	let selectedRows: string[] = [];
	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isAddingRow = false;
	let isDeletingColumn: string | null = null;
	let isDeletingRow: string[] | null = null;
	let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean } = {
		column: null,
		showMenu: false
	};

	$: resetOnUpdate(data.table?.tableData);
	function resetOnUpdate(tableData: GenTable | undefined) {
		selectedRows = [];
		isColumnSettingsOpen = { column: null, showMenu: false };
	}

	function refetchTable() {
		//? Don't refetch while streaming
		if (Object.keys(streamingRows).length === 0) {
			if (searchQuery) {
				handleSearchRows(searchQuery);
			} else {
				searchController?.abort('Duplicate');
				invalidate('action-table:slug').then(() => (isLoadingSearch = false));
			}
		}
	}

	async function handleSearchRows(q: string) {
		if (!tableData) return;

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
					signal: searchController.signal
				}
			);

			const responseBody = await response.json();
			if (response.ok) {
				$genTableRows = responseBody.items;
			} else {
				logger.error('ACTIONTBL_TBL_SEARCHROWS', responseBody);
				console.error(responseBody);
				toast.error('Failed to search rows', {
					description: responseBody.message || JSON.stringify(responseBody)
				});
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
			}
		}

		isLoadingSearch = false;
	}
	const debouncedSearchRows = debounce(handleSearchRows, 300);
</script>

<svelte:head>
	<title>{$page.params.table_id} - Action Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto);`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="action-table"
		class="relative flex flex-col pt-0 min-h-0 max-h-screen min-w-0 overflow-hidden"
	>
		<BreadcrumbsBar />

		<div
			inert={isColumnSettingsOpen.showMenu}
			class="flex items-center justify-between px-4 py-3 gap-2"
		>
			<div class="flex items-center gap-2">
				<a href="/project/{$page.params.project_id}/action-table" class="[all:unset]">
					<Button variant="ghost" class="mr-2 p-0 h-8 rounded-full aspect-square">
						<ArrowLeft size={20} />
					</Button>
				</a>
				<ActionTableIcon class="flex-[0_0_auto] h-6 w-6 text-text" />
				<span
					title={tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
					class="font-medium line-clamp-1 break-all"
				>
					{tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
				</span>
			</div>

			<div class="flex items-center gap-1.5">
				{#if tableData && $genTableRows}
					<InputText
						on:input={({ detail: e }) => {
							//@ts-expect-error Generic type
							debouncedSearchRows(e.target?.value ?? '');
						}}
						bind:value={searchQuery}
						type="search"
						placeholder="Search"
						class="pl-8 h-9 placeholder:not-italic bg-white border-[#E5E5E5] data-dark:border-[#666] rounded-full"
					>
						<svelte:fragment slot="leading">
							{#if isLoadingSearch}
								<div class="absolute top-1/2 left-3 -translate-y-1/2">
									<LoadingSpinner class="h-3" />
								</div>
							{:else}
								<SearchIcon class="absolute top-1/2 left-3 -translate-y-1/2 h-3" />
							{/if}
						</svelte:fragment>
					</InputText>

					<div class="flex items-center gap-4">
						<Button variant="action" on:click={() => (isAddingRow = true)} class="px-3.5 py-0 h-9">
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

					<ActionsDropdown
						tableType="action"
						bind:streamingRows
						bind:selectedRows
						bind:isAddingColumn
						bind:isDeletingRow
						{tableData}
						{refetchTable}
					/>
				{/if}
			</div>
		</div>

		<ActionTable
			bind:userData
			bind:tableData
			bind:selectedRows
			bind:isColumnSettingsOpen
			bind:isDeletingColumn
			{streamingRows}
			{table}
		/>

		{#if tableData && $genTableRows}
			<TablePagination
				tableType="action"
				{table}
				{selectedRows}
				{searchQuery}
				{isColumnSettingsOpen}
			/>
		{/if}

		<ColumnSettings bind:isColumnSettingsOpen tableType="action" />
	</section>
</div>

<AddColumnDialog bind:isAddingColumn tableType="action" />
<AddRowDialog bind:isAddingRow bind:streamingRows {refetchTable} tableType="action" />
<DeleteDialogs bind:isDeletingColumn bind:isDeletingRow tableType="action" />
