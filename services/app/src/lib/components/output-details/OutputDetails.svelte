<script lang="ts">
	import { page } from '$app/state';
	import { ChevronRight } from '@lucide/svelte';
	import converter from '$lib/showdown';
	import { chatCitationPattern } from '$lib/constants';
	import { citationReplacer } from '$lib/utils';

	import References from './References.svelte';
	import { ChatState } from '../../../routes/(main)/chat/chat.svelte';
	import { TableState } from '$lib/components/tables/tablesState.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	let {
		showOutputDetails = $bindable()
	}: {
		showOutputDetails: TableState['showOutputDetails'] | ChatState['showOutputDetails'];
	} = $props();

	let tabItems = $derived(
		[
			{
				id: 'answer',
				title: 'Answer',
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
</script>

<svelte:document onclick={handleCustomBtnClick} />

<div class="z-[1] h-full pb-4 pl-3 pr-3 md:pl-0">
	<div
		style="box-shadow: 0px 2px 4px 0px rgba(0, 0, 0, 0.08);"
		class="flex h-full flex-col rounded-lg border border-[#E4E7EC] bg-white"
	>
		<div
			class="relative flex h-min items-center justify-between space-y-1.5 rounded-t-lg bg-white px-4 py-3 text-left text-lg font-medium text-[#344054] data-dark:bg-[#303338]"
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
			Output details

			<button
				onclick={() => (showOutputDetails = { ...showOutputDetails, open: false, preview: null })}
				class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
			>
				<CloseIcon class="w-6" />
				<span class="sr-only">Close</span>
			</button>
		</div>

		<div
			data-testid="output-details-tabs"
			style="grid-template-columns: repeat({tabItems.length}, minmax(6rem, 1fr));"
			class="relative grid w-full items-end overflow-auto border-b border-[#F2F4F7] text-xs sm:text-sm"
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

		{#if showOutputDetails.activeTab === 'answer'}
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

			<div class="flex h-1 grow flex-col items-center gap-2 overflow-auto px-8 py-4">
				<p class="response-message flex max-w-full flex-col gap-4 whitespace-pre-line text-sm">
					{@html rawHtml}
				</p>
			</div>
		{:else if showOutputDetails.activeTab === 'thinking'}
			{@const rawHtml = converter.makeHtml(showOutputDetails.reasoningContent ?? '')}
			<div class="flex h-1 grow flex-col items-center gap-2 overflow-auto px-8 py-4">
				{#if showOutputDetails.reasoningTime}
					<div class="mb-2 flex select-none items-center gap-2 self-start text-sm text-[#667085]">
						<ChevronRight size={16} />
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
	</div>
</div>
