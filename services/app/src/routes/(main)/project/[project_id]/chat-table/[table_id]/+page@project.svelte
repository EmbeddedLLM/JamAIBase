<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import debounce from 'lodash/debounce';
	import { PlusIcon, Trash2 } from 'lucide-svelte';
	import { browser } from '$app/environment';
	import { afterNavigate, goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import {
		chatTableMode,
		getTableState,
		getTableRowsState
	} from '$lib/components/tables/tablesState.svelte';
	import { db } from '$lib/db';
	import logger from '$lib/logger';
	import type { ChatThreads, GenTable } from '$lib/types';

	import ChatTable from '$lib/components/tables/ChatTable.svelte';
	import { ColumnSettings, TablePagination, TableSorter } from '$lib/components/tables/(sub)';
	import OutputDetailsWrapper from '$lib/components/output-details/OutputDetailsWrapper.svelte';
	import { ActionsDropdown, GenerateButton } from '../../(components)';
	import ModeToggle from './ModeToggle.svelte';
	import ChatMode from './ChatMode.svelte';
	import { AddConversationDialog } from '../(dialogs)';
	import { AddColumnDialog, DeleteDialogs } from '../../(dialogs)';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	let { data } = $props();

	let tableData: GenTable | undefined = $state();
	let tableRowsCount: number | undefined = $state();
	let tableThread: ChatThreads['threads'] = $state({});
	let threadLoaded = $state(false);
	let tableError: { error: number; message: Awaited<typeof data.table>['message'] } | undefined =
		$state();
	let tableLoaded = $state(false);
	let isAddingConversation = $state(false);

	function resetTable() {
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
					const savedColSizes = await db.chat_table.get(page.params.table_id ?? '');
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
	}

	async function fetchThreads() {
		if (!tableData) return;

		const searchParams = new URLSearchParams([['table_id', page.params.table_id ?? '']]);

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/threads?${searchParams}`,
			{
				headers: {
					'x-project-id': page.params.project_id ?? ''
				}
			}
		);
		const responseBody = await response.json();

		if (response.ok) {
			tableThread = responseBody.threads;
		} else {
			logger.error('CHATTBL_TBL_GETTHREAD', responseBody);
			toast.error('Failed to load thread', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		threadLoaded = true;
	}

	// Chat mode only
	let generationStatus = $state<string[] | null>(null);

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
			await invalidate('chat-table:slug');
			isLoadingSearch = false;

			await fetchThreads();

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
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/rows/list?${new URLSearchParams([
					['table_id', tableData.id],
					['limit', (100).toString()],
					['order_by', orderBy ?? 'ID'],
					['order_ascending', orderAsc === 1 ? 'true' : 'false'],
					['search_query', q]
				])}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': page.params.project_id ?? ''
					}
				}
			);

			const responseBody = await response.json();
			if (response.ok) {
				tableRowsState.rows = responseBody.items;
			} else {
				logger.error('CHATTBL_TBL_SEARCHROWS', responseBody);
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

	afterNavigate((url) => {
		// hacky way to unload table, threads won't reload without this
		if (url.from?.url.pathname !== url.to?.url.pathname) tableLoaded = false;
	});
	$effect(() => {
		(data.table, resetTable());
	});
	$effect(() => {
		if (tableLoaded) fetchThreads();
	});
</script>

<svelte:head>
	<title>{page.params.table_id} - Chat Table</title>
</svelte:head>

<section
	id="chat-table"
	class="relative flex h-screen max-h-screen min-h-0 min-w-0 flex-col overflow-hidden pt-0 @container/chat"
>
	<div
		data-testid="table-title-row"
		inert={tableState.columnSettings.isOpen}
		class="grid grid-cols-[minmax(0,max-content)_minmax(min-content,auto)] items-center gap-2 pb-1 pl-3 pr-2 pt-[1.5px] sm:pr-4 sm:pt-3"
	>
		<div class="flex items-center gap-2 text-sm sm:text-base">
			<Button
				variant="ghost"
				href="/project/{page.params.project_id}/chat-table"
				title="Back to chat tables"
				class="hidden aspect-square h-8 items-center justify-center p-0 sm:flex sm:h-9"
			>
				<ArrowBackIcon class="h-7" />
			</Button>
			<ChatTableIcon class="h-6 w-6 flex-[0_0_auto] text-[#475467]" />
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
				<div class="flex items-center gap-1">
					{#if $chatTableMode != 'chat'}
						<div
							title={tableState.selectedRows.length === 0
								? 'Select row to generate output'
								: undefined}
							style="grid-template-columns: minmax(0, 1fr) {tableState.selectedRows.length !== 0
								? 'minmax(0, 1fr)'
								: 'minmax(0, 0fr)'};"
							class="grid place-items-end items-center gap-1 {tableState.selectedRows.length !==
								0 || Object.keys(tableState.streamingRows).length !== 0
								? 'opacity-100'
								: 'opacity-80 grayscale-[90]'} transition-[opacity,grid-template-columns]"
						>
							<GenerateButton
								inert={tableState.selectedRows.length === 0 ? true : undefined}
								tableType="chat"
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
					{:else}
						<Button
							variant="action"
							aria-label="Create table"
							onclick={() => (isAddingConversation = true)}
							class="flex aspect-square h-8 flex-[0_0_auto] items-center gap-2 p-0 sm:h-9 lg:aspect-auto lg:px-3"
						>
							<AddIcon class="h-3.5 w-3.5" />
							<span class="hidden xl:block">New conversation</span>
						</Button>
					{/if}

					<ModeToggle
						validateBeforeChange={() => {
							// Prevent toggling if streaming
							if (generationStatus || Object.keys(tableState.streamingRows).length) {
								return false;
							} else return true;
						}}
						checked={$chatTableMode == 'table'}
						on:checkedChange={(e) => {
							if (e.detail.value) {
								$chatTableMode = 'table';
							} else {
								$chatTableMode = 'chat';
							}
						}}
					/>
				</div>
			{:else}
				<div class="flex items-center gap-1">
					<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[36px] sm:w-[100px]" />
					<Skeleton class="h-[32px] w-[64px] rounded-full sm:h-[36px] sm:w-[72px]" />
				</div>
			{/if}
		</div>
	</div>

	{#if $chatTableMode == 'table'}
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
						class="w-[12rem] place-self-start [&>input]:h-8 [&>input]:sm:h-9"
					/>

					<TableSorter {tableData} tableType="chat" />
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

				<ActionsDropdown tableType="chat" {tableData} {refetchTable} />
			{:else}
				<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
				<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[36px] sm:w-[127px]" />
				<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
			{/if}
		</div>
	{/if}

	{#if $chatTableMode == 'chat'}
		<ChatMode bind:generationStatus {tableData} {tableThread} {threadLoaded} {refetchTable} />
	{:else}
		<ChatTable bind:tableData bind:tableError user={data.user} {refetchTable} />

		{#if !tableError}
			<TablePagination tableType="chat" bind:tableData {tableRowsCount} {searchQuery} />
		{/if}
	{/if}

	<ColumnSettings {tableData} {refetchTable} tableType="chat" />
</section>

<OutputDetailsWrapper bind:showOutputDetails={tableState.showOutputDetails} />
<AddColumnDialog bind:isAddingColumn {tableData} {refetchTable} tableType="chat" />
<AddConversationDialog
	bind:isAddingConversation
	filterByAgent={tableData?.parent_id ?? ''}
	refetchTables={async (tableID) => {
		threadLoaded = false;
		await goto(`${page.url.pathname.substring(0, page.url.pathname.lastIndexOf('/'))}/${tableID}`);
	}}
/>
<DeleteDialogs bind:isDeletingRow {refetchTable} tableType="chat" />
