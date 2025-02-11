<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { browser } from '$app/environment';
	import { afterNavigate, goto, invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { chatTableMode, genTableRows, tableState } from '$lib/components/tables/tablesStore';
	import { db } from '$lib/db';
	import logger from '$lib/logger';
	import type { GenTable, Thread } from '$lib/types';

	import ChatTable from '$lib/components/tables/ChatTable.svelte';
	import { ColumnSettings, TablePagination } from '$lib/components/tables/(sub)';
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
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	export let data;
	$: ({ table, tableRows, userData } = data);
	let tableData: GenTable | undefined;
	let tableRowsCount: number | undefined;
	let tableThread: Thread[][] = [];
	let threadLoaded = false;
	let tableError: { error: number; message: Awaited<typeof table>['message'] } | undefined;
	let tableLoaded = false;
	let isAddingConversation = false;

	$: table, resetTable();
	function resetTable() {
		if (!('then' in table)) return;
		Promise.all([
			table.then(async (tableRes) => {
				tableData = structuredClone(tableRes.data); // Client reorder column
				if (tableRes.error) {
					tableError = { error: tableRes.error, message: tableRes.message };
				}

				if (tableData) tableState.setTemplateCols(tableData.cols);
				if (browser && tableData) {
					const savedColSizes = await db.chat_table.get($page.params.table_id);
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
	}

	$: if (tableLoaded) fetchThreads();
	async function fetchThreads() {
		if (!tableData) return;

		const outputCols = tableData.cols.filter(
			(col) =>
				col.gen_config?.object === 'gen_config.llm' &&
				col.gen_config.multi_turn &&
				/\${User}/g.test(col.gen_config.prompt ?? '')
		);
		const threadsResponses = await Promise.allSettled(
			outputCols.map((col) =>
				fetch(
					`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${tableData!.id}/thread?` +
						new URLSearchParams({
							column_id: col.id
						}),
					{
						headers: {
							'x-project-id': $page.params.project_id
						}
					}
				)
			)
		);
		const threadsBodys = await Promise.allSettled(
			threadsResponses.map((val) => (val.status === 'fulfilled' ? val.value.json() : val.reason))
		);

		tableThread = [];

		const threadLength = threadsBodys.find(
			(promise) => promise.status === 'fulfilled' && promise.value.object === 'chat.thread'
			//@ts-ignore
		)?.value.thread.length!;
		for (let i = 0; i < threadLength; i++) {
			if (i === 0) continue;
			threadsResponses.forEach((promise, idx) => {
				const threadBody = threadsBodys[idx];
				if (promise.status === 'fulfilled') {
					if (threadBody.status === 'fulfilled') {
						if (promise.value.ok) {
							if (threadBody.value.thread[i].role === 'system') return;
							tableThread[i] = [
								...(tableThread[i] ?? []),
								{ ...threadBody.value.thread[i], column_id: outputCols[idx].id }
							];
						} else {
							logger.error('CHATTBL_CHAT_GETERR', threadBody.value);
							tableThread[i] = [
								{
									error: promise.value.status,
									message: threadBody.value,
									column_id: outputCols[idx].id
								}
							];
						}
					} else {
						logger.error('CHATTBL_CHAT_GETPARSE', 'Failed to parse to parse thread response');
						tableThread[i] = [
							{
								error: promise.value.status,
								message: 'Failed to parse thread response',
								column_id: outputCols[idx].id
							}
						];
					}
				} else {
					logger.error('CHATTBL_CHAT_GETUNKNOWN', 'Failed to get thread');
					tableThread[i] = [
						{ error: 500, message: 'Failed to get thread', column_id: outputCols[idx].id }
					];
				}
			});
		}
		tableThread = tableThread.filter((i) => i);

		threadLoaded = true;
	}

	// Chat mode only
	let generationStatus = false;

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
				await invalidate('chat-table:slug');
				isLoadingSearch = false;
			}

			await fetchThreads();

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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${tableData.id}/rows?${new URLSearchParams({
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
</script>

<svelte:head>
	<title>{$page.params.table_id} - Chat Table</title>
</svelte:head>

<section
	id="chat-table"
	class="relative flex flex-col pt-0 min-h-0 h-screen max-h-screen min-w-0 overflow-hidden"
>
	<div
		data-testid="table-title-row"
		inert={$tableState.columnSettings.isOpen}
		class="flex items-center justify-between pl-4 pr-2 sm:pr-4 mt-[1.5px] sm:mt-3 mb-1 gap-2"
	>
		<div class="grow flex items-center gap-2 text-sm sm:text-base">
			<a href="/project/{$page.params.project_id}/chat-table" class="[all:unset] !hidden sm:!block">
				<Button
					variant="ghost"
					title="Back to chat tables"
					class="flex items-center justify-center p-0 h-8 aspect-square"
				>
					<ArrowBackIcon class="h-7" />
				</Button>
			</a>
			<ChatTableIcon class="flex-[0_0_auto] h-6 w-6 text-[#475467]" />
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

			<div class="flex-[0_0_auto] grow flex items-center justify-between gap-1">
				{#if tableLoaded || (tableData && $genTableRows)}
					<div>
						{#if $chatTableMode != 'chat'}
							<SearchBar
								bind:searchQuery
								{isLoadingSearch}
								debouncedSearch={debouncedSearchRows}
								label="Search rows"
							/>
						{/if}
					</div>

					<div class="flex items-center gap-1">
						{#if $chatTableMode != 'chat'}
							<div
								title={$tableState.selectedRows.length === 0
									? 'Select row to generate output'
									: undefined}
								style="grid-template-columns: minmax(0, 1fr) {$tableState.selectedRows.length !== 0
									? 'minmax(0, 1fr)'
									: 'minmax(0, 0fr)'};"
								class="grid place-items-end items-center gap-1 {$tableState.selectedRows.length !==
									0 || Object.keys($tableState.streamingRows).length !== 0
									? 'opacity-100'
									: 'opacity-80 grayscale-[90]'} transition-[opacity,grid-template-columns]"
							>
								<GenerateButton
									inert={$tableState.selectedRows.length === 0 ? true : undefined}
									tableType="chat"
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
									class="flex items-center gap-2 p-0 md:px-3 h-8 sm:h-9 text-[#F04438] bg-[#F2F4F7] hover:bg-[#E4E7EC] focus-visible:bg-[#E4E7EC] active:bg-[#E4E7EC]  aspect-square md:aspect-auto {$tableState
										.selectedRows.length !== 0
										? 'opacity-100'
										: 'opacity-0 pointer-events-none'} transition-opacity"
								>
									<Trash_2 class="h-4 w-4" />

									<span class="hidden md:block">Delete row(s)</span>
								</Button>
							</div>
						{:else}
							<Button
								aria-label="Create table"
								variant="ghost"
								on:click={() => (isAddingConversation = true)}
								class="flex-[0_0_auto] flex items-center gap-2 p-0 lg:px-3 h-8 sm:h-9 !text-[#475467] bg-[#F2F4F7] hover:bg-[#E4E7EC] aspect-square lg:aspect-auto"
							>
								<AddIcon class="h-3.5 w-3.5" />
								<span class="hidden xl:block">New conversation</span>
							</Button>
						{/if}

						<ModeToggle
							validateBeforeChange={() => {
								// Prevent toggling if streaming
								if (generationStatus || Object.keys($tableState.streamingRows).length) {
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

						<ActionsDropdown tableType="chat" bind:isAddingColumn {tableData} {refetchTable} />
					</div>
				{:else}
					<Skeleton class="h-[32px] sm:h-[36px] w-[32px] sm:w-[36px] rounded-full" />
					<div class="flex items-center gap-1">
						<Skeleton class="h-[32px] sm:h-[36px] w-[32px] sm:w-[100px] rounded-full" />
						<Skeleton class="h-[32px] sm:h-[36px] w-[64px] sm:w-[72px] rounded-full" />
						<Skeleton class="h-[32px] sm:h-[36px] w-[32px] sm:w-[36px] rounded-full" />
					</div>
				{/if}
			</div>
		</div>
	</div>

	{#if $chatTableMode == 'chat'}
		<ChatMode
			bind:generationStatus
			{tableData}
			thread={tableThread}
			{threadLoaded}
			{refetchTable}
		/>
	{:else}
		<ChatTable bind:userData bind:tableData bind:tableError {refetchTable} />

		{#if !tableError}
			<TablePagination tableType="chat" bind:tableData {tableRowsCount} {searchQuery} />
		{/if}
	{/if}

	<ColumnSettings {tableData} {refetchTable} tableType="chat" />
</section>

<AddColumnDialog bind:isAddingColumn {tableData} {refetchTable} tableType="chat" />
<AddConversationDialog
	bind:isAddingConversation
	filterByAgent={tableData?.parent_id ?? ''}
	refetchTables={async (tableID) => {
		threadLoaded = false;
		await goto(
			`${$page.url.pathname.substring(0, $page.url.pathname.lastIndexOf('/'))}/${tableID}`
		);
	}}
/>
<DeleteDialogs bind:isDeletingRow {refetchTable} tableType="chat" />
