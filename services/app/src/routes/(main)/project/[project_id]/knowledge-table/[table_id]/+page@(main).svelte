<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import Dropzone from 'svelte-file-dropzone/Dropzone.svelte';
	import { uploadQueue } from '$globalStore';
	import { genTableRows } from '../../tablesStore';
	import logger from '$lib/logger';
	import { knowledgeTableEmbedCols } from '$lib/constants';
	import type { GenTable, GenTableCol } from '$lib/types';

	import KnowledgeTable from './KnowledgeTable.svelte';
	import { ActionsDropdown, ColumnSettings, TablePagination } from '../../(components)';
	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import { UploadingFileDialog } from '../(dialogs)';
	import { AddColumnDialog, AddRowDialog, DeleteDialogs } from '../../(dialogs)';
	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import RowIcon from '$lib/icons/RowIcon.svelte';
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

	let streamingRows: { [key: string]: boolean } = {};

	let isUploadingFile = false;

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
				invalidate('knowledge-table:slug').then(() => (isLoadingSearch = false));
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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/${tableData.id}/rows?${new URLSearchParams(
					{
						limit: (100).toString(),
						search_query: q
					}
				)}`,
				{
					signal: searchController.signal
				}
			);

			const responseBody = await response.json();
			if (response.ok) {
				$genTableRows = responseBody.items;
			} else {
				logger.error('KNOWTBL_TBL_SEARCHROWS', responseBody);
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

	async function handleFilesSelectUpload(e: CustomEvent<any>) {
		const { acceptedFiles, fileRejections } = e.detail;
		const acceptedFilesWithPath = (acceptedFiles as any[]).map<(typeof $uploadQueue.queue)[number]>(
			(file: File) => ({
				file,
				tableType: 'knowledge-table',
				table_id: $page.params.table_id,
				project_id: $page.params.project_id,
				invalidate: refetchTable
			})
		);

		//? Show then hide graphic
		isUploadingFile = true;
		setTimeout(() => (isUploadingFile = false), 3000);

		$uploadQueue.queue = [...$uploadQueue.queue, ...acceptedFilesWithPath];
		$uploadQueue = $uploadQueue;

		if (fileRejections.length) {
			if (
				fileRejections.some((file: any) =>
					file.errors.some((error: any) => error.code == 'file-invalid-type')
				)
			) {
				alert('Files must be of type: pdf, doc, docx, ppt, pptx, xls, xlsx, csv, md, txt');
			} else {
				alert('Some files were rejected');
			}
		}
	}

	function handleUploadClick() {
		(document.querySelector('.dropzone > input[type="file"]') as HTMLElement).click();
	}
</script>

<svelte:head>
	<title>{$page.params.table_id} - Knowledge Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto);`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="knowledge-table"
		class="relative flex flex-col pt-0 min-h-0 max-h-screen min-w-0 overflow-hidden"
	>
		<Dropzone
			on:drop={handleFilesSelectUpload}
			multiple={true}
			accept={['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.txt']}
			inputElement={undefined}
			containerClasses="max-h-[0] !p-0 !border-none overflow-hidden"
		/>

		<BreadcrumbsBar />

		<div
			inert={isColumnSettingsOpen.showMenu}
			class="flex items-center justify-between px-4 py-3 gap-2"
		>
			<div class="flex items-center gap-2">
				<a href="/project/{$page.params.project_id}/knowledge-table" class="[all:unset]">
					<Button variant="ghost" class="mr-2 p-0 h-8 rounded-full aspect-square">
						<ArrowLeft size={20} />
					</Button>
				</a>
				<RowIcon class="flex-[0_0_auto] h-6 w-6 text-text" />
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
						<Button
							variant="action"
							on:click={handleUploadClick}
							class="flex items-center gap-2 p-0 px-3.5 h-9 text-text border border-[#E5E5E5] data-dark:border-[#666] bg-white"
						>
							<svg
								viewBox="0 0 18 18"
								fill="none"
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 aspect-square"
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

							Upload
						</Button>
					</div>

					<ActionsDropdown
						tableType="knowledge"
						bind:streamingRows
						bind:selectedRows
						bind:isAddingColumn
						bind:isDeletingRow
						{tableData}
						{refetchTable}
					/>

					<!-- <Button
						on:click={() => alert('open chunk editor')}
						variant="ghost"
						class="flex items-center gap-2 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
					>
						<ChunkEditorIcon class="mt-0.5 h-4 aspect-square" />
						Chunk Editor
					</Button> -->
				{/if}
			</div>
		</div>

		<KnowledgeTable
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
				tableType="knowledge"
				{table}
				{selectedRows}
				{searchQuery}
				{isColumnSettingsOpen}
			/>
		{/if}

		<ColumnSettings
			bind:isColumnSettingsOpen
			showPromptTab={!knowledgeTableEmbedCols.includes(isColumnSettingsOpen.column?.id ?? '')}
			tableType="knowledge"
		/>
	</section>
</div>

<AddColumnDialog bind:isAddingColumn tableType="knowledge" />
<AddRowDialog bind:isAddingRow bind:streamingRows {refetchTable} tableType="knowledge" />
<DeleteDialogs bind:isDeletingColumn bind:isDeletingRow tableType="knowledge" />
<UploadingFileDialog {isUploadingFile} />
