<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { ArrowDownToLine, Sparkle, Trash2 } from '@lucide/svelte';
	import { page } from '$app/state';
	import converter from '$lib/showdown';
	import { chatCitationPattern } from '$lib/constants';
	import { citationReplacer } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTableCol, GenTableRow } from '$lib/types';

	import References from './References.svelte';
	import { chatState, ChatState } from '../../../routes/(main)/chat/chat.svelte';
	import { Button } from '$lib/components/ui/button';
	import { ColumnTypeTag } from '$lib/components/tables/(sub)';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import {
		getTableState,
		getTableRowsState,
		TableState
	} from '$lib/components/tables/tablesState.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	let {
		showOutputDetails = $bindable()
	}: {
		showOutputDetails: TableState['showOutputDetails'] | ChatState['showOutputDetails'];
	} = $props();

	let column = $derived(
		(page.url.pathname.startsWith('/chat')
			? chatState.conversation?.cols
			: tableState.tableData?.cols
		)?.find((c) => c.id === showOutputDetails.activeCell?.columnID)
	);
	let colType = $derived(!column?.gen_config ? 'input' : 'output');

	let tabItems = $derived(
		[
			{
				id: 'answer',
				title: colType === 'input' ? 'Input' : 'Answer',
				condition: true
			},
			{
				id: 'thinking',
				title: 'Thinking',
				condition: !!showOutputDetails.reasoningContent
			},
			{
				id: 'references',
				title: 'References',
				condition: (showOutputDetails.message?.chunks.length ?? 0) > 0
			}
		].filter((t) => t.condition)
	);
	let tabHighlightPos = $derived(
		(tabItems.findIndex((t) => showOutputDetails.activeTab === t.id) / tabItems.length) * 100
	);

	function handleCustomBtnClick(e: MouseEvent) {
		if (page.url.pathname.startsWith('/chat')) return;

		const target = e.target as HTMLElement;
		if (target.classList.contains('citation-btn')) {
			const columnID = target.getAttribute('data-column');
			const rowID = target.getAttribute('data-row');
			const chunkID = target.getAttribute('data-citation');
			if (columnID && rowID && chunkID) {
				showOutputDetails = {
					...showOutputDetails,
					open: true,
					activeTab: 'references',
					expandChunk: chunkID,
					preview: null
				};
			}
		}
	}

	async function getRawFile(fileUri: string) {
		if (!fileUri) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/raw`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				uris: [fileUri]
			})
		});
		const responseBody = await response.json();

		if (response.ok) {
			window.open(responseBody.urls[0], '_blank');
		} else {
			if (response.status !== 404) {
				logger.error('GETRAW', responseBody);
			}
			toast.error('Failed to get raw file', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}
</script>

<svelte:document
	onclick={handleCustomBtnClick}
	onkeydown={(e) => {
		if (
			page.url.pathname.startsWith('/chat') ||
			!tableRowsState.rows ||
			!tableState.tableData ||
			!column
		)
			return;

		const key = e.key;
		if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) return;

		const rows = tableRowsState.rows;
		const cols = tableState.tableData.cols;
		const currentRowID = showOutputDetails.activeCell?.rowID;
		const currentColID = column?.id;

		function setDetails(row: GenTableRow | undefined, col: GenTableCol) {
			if (!row || !col) return;
			const cell = row[col.id] ?? {};
			const value = cell.value ?? '';
			const chunks = cell.references?.chunks ?? [];
			showOutputDetails = {
				open: true,
				activeCell: { rowID: row.ID, columnID: col.id },
				activeTab:
					col.dtype === 'image'
						? 'image'
						: tableState.streamingRows[row.ID]?.includes(col.id) && !value
							? 'thinking'
							: 'answer',
				message: {
					content: value,
					error: cell.error ?? null,
					chunks,
					fileUrl: tableState.rowThumbs[row.ID]?.[col.id]?.url
				},
				reasoningContent: cell.reasoning_content ?? null,
				reasoningTime: cell.reasoning_time ?? null,
				expandChunk: null,
				preview: null
			};
		}

		const rowIndex = rows.findIndex((r) => r.ID === currentRowID);
		const colIndex = cols.findIndex((c) => c.id === currentColID);

		switch (key) {
			case 'ArrowUp':
				if (rowIndex > 0) setDetails(rows[rowIndex - 1], column);
				break;

			case 'ArrowDown':
				if (rowIndex !== -1 && rowIndex < rows.length - 1) setDetails(rows[rowIndex + 1], column);
				break;

			case 'ArrowLeft': {
				if (colIndex > 2) {
					const prevCol = cols[colIndex - 1];
					const currentRow = rows.find((r) => r.ID === currentRowID);
					setDetails(currentRow, prevCol);
				}
				break;
			}

			case 'ArrowRight': {
				if (colIndex !== -1 && colIndex < cols.length - 1) {
					const nextCol = cols[colIndex + 1];
					const currentRow = rows.find((r) => r.ID === currentRowID);
					setDetails(currentRow, nextCol);
				}
				break;
			}
		}
	}}
/>

<div class="z-[1] h-full pb-4 pl-3 pr-3 md:pl-0">
	<div
		style="box-shadow: 0px 2px 4px 0px rgba(0, 0, 0, 0.08);"
		class="flex h-full flex-col rounded-lg border border-[#E4E7EC] bg-white"
	>
		<div
			class="relative flex h-min items-center justify-between space-y-1.5 rounded-t-lg bg-white px-4 py-3 data-dark:bg-[#303338]"
		>
			<!-- {#if showOutputDetails.preview}
				<div class="flex items-center gap-2">
					<button
						onclick={() => (showOutputDetails = { ...showOutputDetails, preview: null })}
						class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
					>
						<ArrowBackIcon class="w-6 [&>*]:stroke-[#1D2939]" />
					</button>

					<span class="line-clamp-1">
						{showOutputDetails.preview.document_id.split('/').pop()}
					</span>
				</div>
			{:else}
				Citations
			{/if} -->

			{#if showOutputDetails.activeCell}
				<div class="flex items-center gap-2">
					{#if column}
						<ColumnTypeTag
							colType={!column.gen_config ? 'input' : 'output'}
							dtype={column.dtype}
							columnID={column.id}
							genConfig={column.gen_config}
						/>
					{/if}

					<p class="text-[#667085]">{showOutputDetails.activeCell?.columnID}</p>
				</div>
			{:else}
				<p class="text-left text-lg font-medium text-[#344054]">Output details</p>
			{/if}

			<button
				onclick={() => (showOutputDetails = { ...showOutputDetails, open: false, preview: null })}
				class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
			>
				<CloseIcon class="w-6" />
				<span class="sr-only">Close</span>
			</button>
		</div>

		{#if showOutputDetails.message?.error}
			<div class="flex h-1 grow flex-col gap-2 overflow-auto px-8 py-4">
				<p
					class="response-message flex max-w-full flex-col gap-4 whitespace-pre-line text-sm text-[#D92D20]"
				>
					{typeof showOutputDetails.message.error === 'string'
						? showOutputDetails.message.error
						: showOutputDetails.message.error?.message
							? String(showOutputDetails.message.error.message)
							: 'Error'}
				</p>
			</div>
		{:else}
			{#if showOutputDetails.activeTab !== 'image'}
				<div
					data-testid="output-details-tabs"
					style="grid-template-columns: repeat({tabItems.length}, minmax(6rem, 1fr));"
					class="relative grid w-fit items-end overflow-auto border-b border-[#F2F4F7] text-xs sm:text-sm"
				>
					{#each tabItems as { id, title, condition }}
						{#if condition}
							<button
								onclick={() => (showOutputDetails.activeTab = id)}
								class="px-0 py-2 font-medium sm:px-4 {showOutputDetails.activeTab === id
									? 'text-[#344054]'
									: 'text-[#98A2B3]'} text-center transition-colors"
							>
								{title}
							</button>
						{/if}
					{/each}

					<div
						style="width: {(1 / tabItems.length) * 100}%; left: {tabHighlightPos}%;"
						class="absolute bottom-0 h-[3px] bg-secondary transition-[left]"
					></div>
				</div>
			{/if}

			{#if showOutputDetails.activeTab === 'image'}
				<div class="flex h-1 grow flex-col gap-2 p-3">
					<img
						src={showOutputDetails.message?.fileUrl}
						alt=""
						class="max-h-[45vh] object-contain"
					/>

					<p
						title={showOutputDetails.message?.content.split('/').pop()}
						class="break-all rounded text-sm text-[#667085]"
					>
						{showOutputDetails.message?.content.split('/').pop()}
					</p>

					<div class="flex gap-1">
						<Button
							variant="ghost"
							title="Download file"
							onclick={() => getRawFile(showOutputDetails.message?.content ?? '')}
							class="h-8 w-max gap-2 rounded-md border border-[#E4E7EC] bg-white px-2 font-normal text-[#667085] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:bg-[#F9FAFB] hover:text-[#667085]"
						>
							<ArrowDownToLine class="h-3.5 w-3.5" />
							Download
						</Button>

						{#if showOutputDetails.activeCell?.rowID}
							<Button
								variant="ghost"
								title="Delete file"
								onclick={() => {
									tableState.deletingFile = {
										rowID: showOutputDetails.activeCell?.rowID ?? '',
										columnID: showOutputDetails.activeCell?.columnID ?? '',
										fileUri: showOutputDetails.message?.content ?? ''
									};
								}}
								class="h-8 w-max gap-2 rounded-md border border-[#E4E7EC] bg-white px-2 font-normal text-[#F04438] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:bg-[#F9FAFB] hover:text-[#F04438]"
							>
								<Trash2 class="h-3.5 w-3.5" />
								Delete
							</Button>
						{/if}
					</div>
				</div>
			{:else if showOutputDetails.activeTab === 'answer'}
				{@const rawHtml = converter
					.makeHtml(showOutputDetails.message?.content ?? '')
					.replaceAll(chatCitationPattern, (match, word) =>
						citationReplacer(
							match,
							word,
							showOutputDetails.activeCell?.columnID ?? '',
							showOutputDetails.activeCell?.rowID ?? '',
							showOutputDetails.message?.chunks ?? []
						)
					)}

				<div class="flex h-1 grow flex-col gap-2 overflow-auto px-8 py-4">
					<p class="response-message flex max-w-full flex-col gap-4 whitespace-pre-line text-sm">
						{@html rawHtml}
					</p>
				</div>
			{:else if showOutputDetails.activeTab === 'thinking'}
				{@const rawHtml = converter.makeHtml(showOutputDetails.reasoningContent ?? '')}
				<div class="flex h-1 grow flex-col gap-2 overflow-auto px-8 py-4">
					{#if showOutputDetails.reasoningTime}
						<div class="mb-2 flex select-none items-center gap-2 self-start text-sm text-[#667085]">
							<Sparkle size={16} />
							Thought for {showOutputDetails.reasoningTime.toFixed()} second{Number(
								showOutputDetails.reasoningTime.toFixed()
							) > 1
								? 's'
								: ''}
						</div>
					{/if}

					<p
						class="response-message flex max-w-full flex-col gap-4 whitespace-pre-line text-sm text-[#475467]"
					>
						{@html rawHtml}
					</p>
				</div>
			{:else if showOutputDetails.activeTab === 'references'}
				<References bind:showReferences={showOutputDetails} />
			{/if}
		{/if}
	</div>
</div>
