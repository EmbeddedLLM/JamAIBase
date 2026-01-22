<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import debounce from 'lodash/debounce';
	import { PlusIcon, Trash2 } from '@lucide/svelte';
	import { browser } from '$app/environment';
	import { goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import { uploadQueue } from '$globalStore';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import { db } from '$lib/db';
	import logger from '$lib/logger';
	import { knowledgeTableEmbedCols, knowledgeTableFiletypes } from '$lib/constants';
	import type { GenTable } from '$lib/types';

	import KnowledgeTable from '$lib/components/tables/KnowledgeTable.svelte';
	import { ColumnSettings, TablePagination, TableSorter } from '$lib/components/tables/(sub)';
	import OutputDetailsWrapper from '$lib/components/output-details/OutputDetailsWrapper.svelte';
	import { ActionsDropdown, GenerateButton } from '../../(components)';
	import { UploadingFileDialog } from '../(dialogs)';
	import { AddColumnDialog, DeleteDialogs } from '../../(dialogs)';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import KnowledgeTableIcon from '$lib/icons/KnowledgeTableIcon.svelte';
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
					const savedColSizes = await db.knowledge_table.get(page.params.table_id!);
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
								error: activeCell.error ?? null,
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

	let isUploadingFile = $state(false);
	let filesDragover = $state(false);

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
			await invalidate('knowledge-table:slug');
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
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/rows/list?${new URLSearchParams([
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
				logger.error('KNOWTBL_TBL_SEARCHROWS', responseBody);
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

	async function handleFilesUpload(files: File[]) {
		document
			.querySelectorAll('input[type="file"]')
			.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (!tableData || !tableRowsState.rows) return;

		if (files.length === 0) return;
		if (
			files.some(
				(file) =>
					!knowledgeTableFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(`Files must be of type: ${knowledgeTableFiletypes.join(', ').replaceAll('.', '')}`);
			return;
		}

		const filesToQueue = files.map<(typeof $uploadQueue.queue)[number]>((file) => {
			const formData = new FormData();
			formData.append('file', file, file.name);
			if (page.params.table_id) formData.append('table_id', page.params.table_id);

			return {
				file,
				request: {
					method: 'POST',
					url: `${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/embed_file`,
					data: formData,
					headers: {
						'Content-Type': 'multipart/form-data'
					}
				},
				completeText: 'Embedding file...',
				successText: `Uploaded to table: ${page.params.table_id}`,
				invalidate: refetchTable
			};
		});

		//? Show then hide graphic
		isUploadingFile = true;
		setTimeout(() => (isUploadingFile = false), 3000);

		$uploadQueue = {
			...$uploadQueue,
			queue: [...$uploadQueue.queue, ...filesToQueue]
		};
	}

	const handleUploadClick = () =>
		(document.querySelector('input[type="file"]') as HTMLElement).click();
	const handleDragLeave = () => (filesDragover = false);
	$effect(() => {
		(data.table, resetTable());
	});
</script>

<svelte:head>
	<title>{page.params.table_id} - Knowledge Table</title>
</svelte:head>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<section
	ondragover={(e) => {
		e.preventDefault();
		if (document.querySelector('[data-editing="true"]')) return;
		if (e.dataTransfer?.items) {
			if ([...e.dataTransfer.items].some((item) => item.kind === 'file')) {
				filesDragover = true;
			}
		}
	}}
	ondragleave={debounce(handleDragLeave, 50)}
	ondrop={(e) => {
		e.preventDefault();
		filesDragover = false;
		if (document.querySelector('[data-editing="true"]')) return;
		if (e.dataTransfer?.items) {
			handleFilesUpload(
				[...e.dataTransfer.items]
					.map((item) => {
						if (item.kind === 'file') {
							const itemFile = item.getAsFile();
							if (itemFile) {
								return itemFile;
							} else {
								return [];
							}
						} else {
							return [];
						}
					})
					.flat()
			);
		} else {
			handleFilesUpload([...(e.dataTransfer?.files ?? [])]);
		}
	}}
	id="knowledge-table"
	class="relative flex h-screen max-h-screen min-h-0 min-w-0 flex-col overflow-hidden pt-0"
>
	<div
		class="pointer-events-none absolute bottom-0 left-0 right-0 top-0 z-[100] bg-black/40 p-4 transition-opacity {filesDragover
			? 'opacity-100'
			: 'opacity-0'}"
	>
		<div class="h-full w-full rounded-lg border-4 border-dashed border-secondary"></div>
		<div
			class="absolute bottom-6 left-1/2 flex h-20 w-[20rem] -translate-x-1/2 items-center justify-center rounded-md bg-white"
		>
			<p class="font-medium">Drop file(s) to upload to knowledge table</p>
		</div>
	</div>

	<input
		type="file"
		accept={knowledgeTableFiletypes.join(',')}
		onchange={(e) => {
			e.preventDefault();
			handleFilesUpload([...(e.currentTarget.files ?? [])]);
		}}
		multiple
		class="max-h-[0] overflow-hidden !border-none !p-0"
	/>

	<div
		data-testid="table-title-row"
		inert={tableState.columnSettings.isOpen}
		class="grid grid-cols-[minmax(0,max-content)_minmax(min-content,auto)] items-center gap-2 pb-2 pl-3 pr-2 pt-1.5 sm:pr-4 sm:pt-3"
	>
		<div class="flex items-center gap-2 text-sm sm:text-base">
			<Button
				variant="ghost"
				href="/project/{page.params.project_id}/knowledge-table"
				title="Back to knowledge tables"
				class="hidden aspect-square h-8 items-center justify-center p-0 sm:flex sm:h-9"
			>
				<ArrowBackIcon class="h-7" />
			</Button>
			<KnowledgeTableIcon class="h-6 w-6 flex-[0_0_auto] text-[#475467]" />
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

		<div style="grid-template-columns: auto;" class="grid w-full place-items-end gap-1">
			{#if tableLoaded || (tableData && tableRowsState.rows)}
				<div class="relative h-full w-full sm:translate-y-px">
					<div class="absolute right-0 top-1/2 flex -translate-y-1/2 items-center gap-1">
						<div
							title={tableState.selectedRows.length === 0
								? 'Select row to generate output'
								: undefined}
						>
							<GenerateButton
								inert={tableState.selectedRows.length === 0 ? true : undefined}
								tableType="knowledge"
								{tableData}
								{refetchTable}
								class="{tableState.selectedRows.length !== 0 ||
								Object.keys(tableState.streamingRows).length !== 0
									? 'opacity-100'
									: 'bg-[#E4E7EC] opacity-80 [&>div]:bg-[#E4E7EC] [&_*]:!text-[#98A2B3]'} transition-opacity"
							/>
						</div>

						{#if tableState.selectedRows.length === 0}
							<Button
								variant="action"
								title="Upload"
								onclick={handleUploadClick}
								class="flex aspect-square h-8 items-center gap-2 p-0 sm:h-9 lg:aspect-auto lg:px-3"
							>
								<svg
									viewBox="0 0 18 18"
									fill="none"
									xmlns="http://www.w3.org/2000/svg"
									class="aspect-square h-5"
								>
									<path
										d="M11.2502 3.375C10.1328 3.37492 9.04067 3.70752 8.11303 4.33043C7.18538 4.95333 6.46421 5.83833 6.0414 6.87263C5.50039 6.73435 4.93615 6.71274 4.38614 6.80921C3.83614 6.90568 3.31294 7.11804 2.85128 7.43218C2.38962 7.74632 2.00006 8.15507 1.70845 8.63128C1.41684 9.1075 1.22986 9.64029 1.15992 10.1943C1.08997 10.7483 1.13867 11.3109 1.30276 11.8446C1.46686 12.3784 1.74261 12.8711 2.1117 13.2901C2.4808 13.7092 2.9348 14.0449 3.44357 14.275C3.95235 14.5052 4.50425 14.6245 5.06265 14.625H5.62515C5.77434 14.625 5.91741 14.5657 6.0229 14.4602C6.12839 14.3548 6.18765 14.2117 6.18765 14.0625C6.18765 13.9133 6.12839 13.7702 6.0229 13.6648C5.91741 13.5593 5.77434 13.5 5.62515 13.5H5.06265C4.6457 13.4996 4.23405 13.4066 3.85749 13.2275C3.48094 13.0485 3.1489 12.788 2.88541 12.4648C2.62192 12.1417 2.43357 11.764 2.33401 11.3591C2.23444 10.9542 2.22614 10.5323 2.30971 10.1238C2.39328 9.7153 2.56663 9.3305 2.81721 8.99724C3.06779 8.66399 3.38933 8.39062 3.75855 8.19692C4.12778 8.00322 4.53545 7.89404 4.95207 7.87727C5.36868 7.86051 5.78381 7.93659 6.1674 8.1C6.24061 8.13136 6.31963 8.14682 6.39926 8.14535C6.47888 8.14388 6.55728 8.12553 6.62928 8.0915C6.70128 8.05746 6.76523 8.00853 6.8169 7.94794C6.86858 7.88734 6.90679 7.81647 6.92903 7.74C7.13196 7.04517 7.49951 6.40955 8.0005 5.88707C8.50148 5.36459 9.12112 4.97068 9.80682 4.73876C10.4925 4.50684 11.224 4.44376 11.9393 4.55487C12.6546 4.66599 13.3325 4.94801 13.9156 5.37701C14.4986 5.80601 14.9695 6.36933 15.2884 7.01917C15.6073 7.669 15.7647 8.38617 15.7473 9.10982C15.7299 9.83347 15.5381 10.5422 15.1884 11.176C14.8386 11.8097 14.3411 12.3497 13.7381 12.7502C13.6766 12.7911 13.6237 12.8437 13.5825 12.905C13.5413 12.9663 13.5126 13.0352 13.498 13.1076C13.4834 13.18 13.4832 13.2546 13.4974 13.3271C13.5116 13.3996 13.54 13.4686 13.5809 13.5301C13.6218 13.5916 13.6744 13.6445 13.7357 13.6857C13.797 13.7269 13.8658 13.7556 13.9383 13.7702C14.0107 13.7848 14.0853 13.785 14.1578 13.7708C14.2303 13.7566 14.2992 13.7282 14.3608 13.6873C15.1343 13.1744 15.7688 12.4778 16.2076 11.6599C16.6463 10.842 16.8757 9.92816 16.8752 9C16.8752 5.89331 14.3568 3.375 11.2502 3.375Z"
										fill="currentColor"
									/>
									<path
										d="M10.2696 10.32C10.2168 10.2588 10.1514 10.2097 10.0779 10.1761C10.0045 10.1424 9.9246 10.125 9.84378 10.125C9.76297 10.125 9.6831 10.1424 9.60962 10.1761C9.53614 10.2097 9.47077 10.2588 9.41797 10.32L7.44922 12.5998C7.40095 12.6557 7.36416 12.7206 7.34096 12.7907C7.31776 12.8608 7.3086 12.9349 7.31401 13.0085C7.31941 13.0822 7.33928 13.1541 7.37247 13.2201C7.40566 13.2861 7.45152 13.3449 7.50744 13.3932C7.56336 13.4414 7.62824 13.4782 7.69837 13.5014C7.76851 13.5246 7.84252 13.5338 7.9162 13.5284C7.98987 13.523 8.06176 13.5031 8.12776 13.4699C8.19376 13.4367 8.25257 13.3909 8.30084 13.335L9.28128 12.1998V15.1878C9.28128 15.337 9.34054 15.4801 9.44603 15.5856C9.55152 15.6911 9.6946 15.7503 9.84378 15.7503C9.99297 15.7503 10.136 15.6911 10.2415 15.5856C10.347 15.4801 10.4063 15.337 10.4063 15.1878V12.1998L11.3867 13.335C11.435 13.3909 11.4938 13.4367 11.5598 13.4699C11.6258 13.5031 11.6977 13.523 11.7714 13.5284C11.845 13.5338 11.9191 13.5246 11.9892 13.5014C12.0593 13.4782 12.1242 13.4414 12.1801 13.3932C12.236 13.3449 12.2819 13.2861 12.3151 13.2201C12.3483 13.1541 12.3681 13.0822 12.3736 13.0085C12.379 12.9349 12.3698 12.8608 12.3466 12.7907C12.3234 12.7206 12.2866 12.6557 12.2383 12.5998L10.2696 10.32Z"
										fill="currentColor"
									/>
								</svg>

								<span class="hidden lg:block">Upload</span>
							</Button>
						{:else}
							<Button
								variant="action"
								title="Delete row(s)"
								onclick={() => (isDeletingRow = tableState.selectedRows)}
								class="flex aspect-square h-8 items-center gap-2 p-0 text-[#F04438] sm:h-9 lg:aspect-auto lg:px-3"
							>
								<Trash2 class="h-4 w-4" />

								<span class="hidden lg:block">Delete row(s)</span>
							</Button>
						{/if}
					</div>
				</div>

				<!-- <Button
						on:click={() => alert('open chunk editor')}
						variant="ghost"
						class="flex items-center gap-2 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
					>
						<ChunkEditorIcon class="mt-0.5 h-4 aspect-square" />
						Chunk Editor
					</Button> -->
			{:else}
				<div class="flex gap-1">
					<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[38px] sm:w-[38px] lg:w-[100px]" />
					<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[38px] sm:w-[38px] lg:w-[100px]" />
				</div>
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
					class="w-[12rem] place-self-start [&>input]:h-8 [&>input]:sm:h-9"
				/>

				<TableSorter {tableData} tableType="knowledge" />
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

			<ActionsDropdown tableType="knowledge" {tableData} {refetchTable} />
		{:else}
			<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
			<Skeleton class="h-[32px] w-[32px] rounded-full sm:h-[36px] sm:w-[127px]" />
			<Skeleton class="h-[32px] w-[32px] place-self-start rounded-full sm:h-[36px] sm:w-[36px]" />
		{/if}
	</div>

	<KnowledgeTable bind:tableData bind:tableError user={data.user} {refetchTable} />

	{#if !tableError}
		<TablePagination tableType="knowledge" bind:tableData {tableRowsCount} {searchQuery} />
	{/if}

	<ColumnSettings
		{tableData}
		{refetchTable}
		showPromptTab={!knowledgeTableEmbedCols.includes(tableState.columnSettings.column?.id ?? '')}
		tableType="knowledge"
	/>
</section>

<OutputDetailsWrapper bind:showOutputDetails={tableState.showOutputDetails} />
<AddColumnDialog bind:isAddingColumn {tableData} {refetchTable} tableType="knowledge" />
<DeleteDialogs bind:isDeletingRow {refetchTable} tableType="knowledge" />
<UploadingFileDialog {isUploadingFile} />
