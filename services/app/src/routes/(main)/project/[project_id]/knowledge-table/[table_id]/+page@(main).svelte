<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Dropzone from 'svelte-file-dropzone/Dropzone.svelte';
	import { showRightDock, uploadQueue } from '$globalStore';
	import { genTableRows } from '../../tablesStore';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol, GenTableStreamEvent } from '$lib/types';

	import KnowledgeTable from './KnowledgeTable.svelte';
	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import PastKnowledgeTables from './PastKnowledgeTables.svelte';
	import { AddColumnDialog, AddRowDialog, DeleteDialogs } from '../../(dialogs)';
	import { AddTableDialog, UploadingFileDialog } from './(dialogs)';
	import ColumnSettings from './ColumnSettings.svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import DblArrowRightIcon from '$lib/icons/DblArrowRightIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import RowIcon from '$lib/icons/RowIcon.svelte';
	import ArrowFilledRightIcon from '$lib/icons/ArrowFilledRightIcon.svelte';
	import ColumnIcon from '$lib/icons/ColumnIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';

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

	let rightDockButton: HTMLButtonElement;
	let showRightDockButton = false;

	let selectedRows: string[] = [];

	let isAddingTable = false;
	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isAddingRow = false;
	let isDeletingTable: string | null = null;
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
			invalidate('knowledge-table:slug');
		}
	}

	async function handleRegenRow(toRegenRowIds: string[]) {
		if (!tableData || !$genTableRows) return;

		streamingRows = {
			...streamingRows,
			...toRegenRowIds.reduce((acc, curr) => ({ ...acc, [curr]: true }), {})
		};

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: $genTableRows!.find((row) => row.ID === toRegenRowId)!
		}));
		genTableRows.clearOutputs(tableData, toRegenRowIds);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_ROW_REGEN', responseBody);
			toast.error('Failed to regenerate row', {
				description: responseBody.message || JSON.stringify(responseBody)
			});

			//? Revert back to original value
			genTableRows.revert(originalValues);
		} else {
			//Delete all data except for inputs
			genTableRows.clearOutputs(tableData, toRegenRowIds);

			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error('KNOWTBL_ROW_REGENSTREAMPARSE', {
									parsing: sumValue,
									error: err
								});
								continue;
							}

							if (parsedValue.object === 'gen_table.completion.chunk') {
								if (
									parsedValue.choices[0].finish_reason &&
									parsedValue.choices[0].finish_reason === 'error'
								) {
									logger.error('KNOWTBL_ROW_REGENSTREAM', parsedValue);
									console.error('STREAMING_ERROR', parsedValue);
									alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
								} else {
									//* Add chunk to active row'
									genTableRows.stream(
										parsedValue.row_id,
										parsedValue.output_column_name,
										parsedValue.choices[0].message.content ?? ''
									);
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					// logger.error('ACTIONTBL_ROW_REGENSTREAM', err);
					console.error(err);

					//? Below necessary for retry
					for (const toRegenRowId of toRegenRowIds) {
						delete streamingRows[toRegenRowId];
					}
					streamingRows = streamingRows;

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		for (const toRegenRowId of toRegenRowIds) {
			delete streamingRows[toRegenRowId];
		}
		streamingRows = streamingRows;

		refetchTable();
	}

	async function handleFilesSelectUpload(e: CustomEvent<any>) {
		const { acceptedFiles, fileRejections } = e.detail;
		const acceptedFilesWithPath = (acceptedFiles as any[]).map((file: File) => ({
			file,
			uploadTo: 'knowledge-table',
			table_id: $page.params.table_id
		}));

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

	//! Listen to state update
	$: if (typeof $uploadQueue.queue.length === 'number' && browser) {
		// FIXME: Table wont refetch if rows are streaming while uploading
		refetchTable();
	}

	function handleUploadClick() {
		(document.querySelector('.dropzone > input[type="file"]') as HTMLElement).click();
	}

	function mouseMoveListener(e: MouseEvent) {
		const tableArea = document.getElementById('knowledge-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton.contains(el) ||
			(tableArea?.contains(el) && tableArea?.offsetWidth - (e.clientX - tableArea?.offsetLeft) < 75)
		) {
			showRightDockButton = true;
		} else {
			showRightDockButton = false;
		}
	}
</script>

<svelte:window on:mousemove={mouseMoveListener} />

<svelte:head>
	<title>{$page.params.table_id} - Knowledge Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto) ${$showRightDock ? '20rem' : '0rem'};`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="knowledge-table"
		class="relative flex flex-col pt-0 pb-12 min-h-0 max-h-screen min-w-0 overflow-hidden"
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
				<RowIcon class="flex-[0_0_auto] h-6 w-6 text-secondary" />
				<span class="font-medium line-clamp-1">
					{tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
				</span>
			</div>

			<div class="flex items-center gap-1.5">
				{#if tableData && $genTableRows}
					<div class="flex items-center gap-4">
						<Button
							on:click={handleUploadClick}
							class="flex items-center gap-2 px-2.5 py-0 h-9 text-text bg-black/[0.04] data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1]"
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

					<DropdownMenu.Root>
						<DropdownMenu.Trigger asChild let:builder>
							<Button
								builders={[builder]}
								variant="ghost"
								class="flex gap-3 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
							>
								Actions
								<ArrowFilledRightIcon class="h-2.5 w-2.5" />
							</Button>
						</DropdownMenu.Trigger>
						<DropdownMenu.Content alignOffset={-40} transitionConfig={{ x: 5, y: -5 }}>
							<DropdownMenu.Group>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
										column
									</span>
								</DropdownMenu.Item>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#A67835] data-dark:text-[#DA9F47]">output</span>
										column
									</span>
								</DropdownMenu.Item>
							</DropdownMenu.Group>
							{#if selectedRows.length}
								<DropdownMenu.Separator />
								<DropdownMenu.Group>
									{#if selectedRows.length}
										<DropdownMenu.Item
											on:click={() => {
												handleRegenRow(selectedRows.filter((i) => !streamingRows[i]));
												selectedRows = [];
											}}
											class="pl-[5px]"
										>
											<RegenerateIcon class="h-5 w-5 mr-[5px]" />
											Regenerate row
										</DropdownMenu.Item>
									{/if}
									<DropdownMenu.Item on:click={() => (isDeletingRow = selectedRows)}>
										<Trash2 class="h-3.5 w-3.5 mr-2 mb-[2px]" />
										Delete row(s)
									</DropdownMenu.Item>
								</DropdownMenu.Group>
							{/if}
						</DropdownMenu.Content>
					</DropdownMenu.Root>

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

		<ColumnSettings bind:isColumnSettingsOpen bind:isDeletingColumn />
	</section>

	<section
		class="relative z-[1] flex flex-col gap-2 min-h-0 bg-white data-dark:bg-[#303338] border-l border-[#DDD] data-dark:border-[#2A2A2A]"
	>
		<!-- Close right dock button -->
		<div
			class="absolute top-1/2 -translate-y-1/2 -left-16 flex items-center justify-end h-[80%] w-16 overflow-hidden pointer-events-none"
		>
			<button
				bind:this={rightDockButton}
				title="Show/hide knowledge table history"
				on:click={() => ($showRightDock = !$showRightDock)}
				on:focusin={() => (showRightDockButton = true)}
				on:focusout={() => (showRightDockButton = false)}
				class={`p-1 bg-white data-dark:bg-[#303338] border border-[#DDD] data-dark:border-[#2A2A2A] rounded-l-xl ${
					showRightDockButton ? 'translate-x-0' : 'translate-x-11'
				} transition-transform duration-300 pointer-events-auto`}
			>
				<DblArrowRightIcon class={`w-8 h-8 ${!$showRightDock && 'rotate-180'}`} />
			</button>
		</div>

		<Button
			disabled={!$showRightDock}
			variant="outline"
			title="New table"
			on:click={() => (isAddingTable = true)}
			class="flex items-center gap-3 m-4 mx-6 mt-10 p-4 text-secondary hover:text-secondary text-center border-2 border-secondary bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-lg whitespace-nowrap overflow-hidden"
		>
			<AddIcon class="w-3 h-3" />
			New table
		</Button>

		<PastKnowledgeTables bind:isDeletingTable />
	</section>
</div>

<AddTableDialog bind:isAddingTable />
<AddColumnDialog bind:isAddingColumn tableType="knowledge" />
<AddRowDialog bind:isAddingRow bind:streamingRows {refetchTable} tableType="knowledge" />
<DeleteDialogs
	bind:isDeletingTable
	bind:isDeletingColumn
	bind:isDeletingRow
	tableType="knowledge"
/>
<UploadingFileDialog {isUploadingFile} />
