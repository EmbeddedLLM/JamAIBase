<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { MediaQuery } from 'svelte/reactivity';
	import { ChevronRight } from '@lucide/svelte';
	import { chatState } from '../../../chat.svelte';
	import { chatCitationPattern } from '$lib/constants';
	import type { ChatThread } from '$lib/types';

	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import PdfViewer from './PDFViewer.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	const bigScreen = new MediaQuery('min-width: 768px');

	let {
		showReferences = $bindable()
	}: {
		showReferences: {
			open: boolean;
			message: { columnID: string; rowID: string } | null;
			expandChunk: string | null;
			preview: NonNullable<ChatThread['thread'][number]['references']>['chunks'][number] | null;
		};
	} = $props();

	let expandChunk = $state<string | null>(null);

	function extractCitationNumbers(text: string) {
		const numbers = new Set<number>();

		let match;
		while ((match = chatCitationPattern.exec(text)) !== null) {
			const numberMatches = match[1].match(/@(\d+)/g);
			if (numberMatches) {
				numberMatches.forEach((numMatch) => {
					const number = parseInt(numMatch.substring(1));
					numbers.add(number);
				});
			}
		}

		return numbers;
	}

	const getDocUrl = async (uri: string) => {
		const getDocUrl = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/raw`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				uris: [uri]
			})
		});
		const getDocUrlBody = await getDocUrl.json();

		if (getDocUrl.ok) {
			return getDocUrlBody.urls[0] as string;
		}
	};
	let docUrl = $derived.by(async () => {
		if (showReferences.message && showReferences.preview) {
			const threadItem = chatState.messages[showReferences.message.columnID].thread.find(
				(item) => item.references && item.row_id === showReferences.message?.rowID
			);
			if (threadItem?.references) {
				return getDocUrl(
					threadItem.references.chunks.find((c) => c.chunk_id === showReferences.preview?.chunk_id)
						?.document_id ?? ''
				);
			}
		}
	});
</script>

<div class="z-[1] pb-4 pl-0 pr-3">
	<div
		style="box-shadow: 0px 2px 4px 0px rgba(0, 0, 0, 0.08);"
		class="flex h-full flex-col rounded-lg border border-[#E4E7EC] bg-white"
	>
		<div
			class="relative flex h-min items-center justify-between space-y-1.5 rounded-t-lg bg-white px-4 py-3 text-left text-lg font-medium text-[#344054] data-dark:bg-[#303338]"
		>
			{#if showReferences.preview}
				<div class="flex items-center gap-2">
					<button
						onclick={() => (showReferences = { ...showReferences, preview: null })}
						class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
					>
						<ArrowBackIcon class="w-6 [&>*]:stroke-[#1D2939]" />
					</button>

					<span class="line-clamp-1">
						{showReferences.preview.document_id.split('/').pop()}
					</span>
				</div>
			{:else}
				Citations
			{/if}

			<button
				onclick={() => (showReferences = { ...showReferences, open: false, preview: null })}
				class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
			>
				<CloseIcon class="w-6" />
				<span class="sr-only">Close</span>
			</button>
		</div>

		<div class="flex h-1 grow flex-col items-center gap-2 overflow-auto px-1 pb-1">
			{#if !showReferences.preview}
				{@const threadItem = chatState.messages[
					showReferences.message?.columnID ?? ''
				]?.thread?.find((item) => item.references && item.row_id === showReferences.message?.rowID)}
				{@const citedRefs = extractCitationNumbers(
					typeof threadItem?.content === 'string'
						? threadItem.content
						: threadItem?.content
								.filter((c) => c.type === 'text')
								.map((c) => c.text)
								.join('') ?? ''
				)}
				{#each threadItem?.references?.chunks ?? [] as chunk, chunkIndex (chunk.chunk_id)}
					{#if citedRefs.has(chunkIndex)}
						<div class="flex flex-col">
							<button
								onclick={() =>
									(showReferences.expandChunk =
										showReferences.expandChunk === chunk.chunk_id ? null : chunk.chunk_id)}
								class="relative flex items-center gap-1 rounded-lg px-3 py-2 pl-8 text-left font-medium text-[#667085] hover:bg-[#F2F4F7]"
							>
								<ChevronRight
									class="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[#344054] transition-transform {showReferences.expandChunk ===
										chunk.chunk_id && 'rotate-90'}"
								/>
								<div
									class="flex aspect-square h-5 w-5 items-center justify-center rounded-full bg-[#FFD8DF] text-xs text-[#475467]"
								>
									{chunkIndex + 1}
								</div>
								<span
									title={chunk.document_id.split('/').at(-1) ?? 'Document Title'}
									class="line-clamp-1 text-sm"
								>
									{chunk.document_id.split('/').at(-1) ?? 'Document Title'}
								</span>
							</button>

							<div
								class="grid {showReferences.expandChunk === chunk.chunk_id
									? 'grid-rows-[1fr]'
									: 'grid-rows-[0fr]'} overflow-hidden transition-[grid-template-rows]"
							>
								<div class="min-h-0 overflow-hidden">
									<button
										onclick={async () => {
											if (bigScreen.current) {
												showReferences = { ...showReferences, preview: chunk };
											} else {
												const documentUrl = await getDocUrl(chunk.document_id);
												if (documentUrl) window.open(documentUrl, '_blank')?.focus();
											}
										}}
										class="rounded-lg py-4 pl-8 pr-3 hover:bg-[#F2F4F7]"
									>
										<p class="text-left text-[#344054]">
											{chunk.page !== null ? `[${chunk.page}]` : ''}
											{chunk.title || '(no title)'}
										</p>
										<p class="text-left text-sm text-[#667085]">{chunk.text}</p>
									</button>
								</div>
							</div>
						</div>
					{/if}
				{/each}

				<hr class="w-full" />

				<span class="self-start px-2 font-medium text-[#475467]">All sources</span>

				{#each chatState.messages[showReferences.message?.columnID ?? '']?.thread?.find((item) => item.references && item.row_id === showReferences.message?.rowID)?.references?.chunks ?? [] as chunk, chunkIndex (chunk.chunk_id)}
					<div class="flex flex-col">
						<button
							onclick={() => (expandChunk = expandChunk === chunk.chunk_id ? null : chunk.chunk_id)}
							class="relative flex items-center gap-1 rounded-lg px-3 py-2 pl-16 text-left font-medium text-[#667085] hover:bg-[#F2F4F7]"
						>
							<ChevronRight
								class="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[#344054] transition-transform {expandChunk ===
									chunk.chunk_id && 'rotate-90'}"
							/>
							<DocumentFilledIcon
								class="absolute left-8 top-1/2 h-7 w-7 -translate-y-1/2 text-[#A62050]"
							/>
							<span
								title={chunk.document_id.split('/').at(-1) ?? 'Document Title'}
								class="line-clamp-1"
							>
								{chunk.document_id.split('/').at(-1) ?? 'Document Title'}
							</span>
						</button>

						<div
							class="grid {expandChunk === chunk.chunk_id
								? 'grid-rows-[1fr]'
								: 'grid-rows-[0fr]'} overflow-hidden transition-[grid-template-rows]"
						>
							<div class="min-h-0 overflow-hidden">
								<button
									onclick={async () => {
										if (bigScreen.current) {
											showReferences = { ...showReferences, preview: chunk };
										} else {
											const documentUrl = await getDocUrl(chunk.document_id);
											if (documentUrl) window.open(documentUrl, '_blank')?.focus();
										}
									}}
									class="rounded-lg py-4 pl-8 pr-3 hover:bg-[#F2F4F7]"
								>
									<p class="text-left text-[#344054]">
										{chunk.page !== null ? `[${chunk.page}]` : ''}
										{chunk.title || '(no title)'}
									</p>
									<p class="text-left text-sm text-[#667085]">{chunk.text}</p>
								</button>
							</div>
						</div>
					</div>
				{/each}
			{:else}
				{#await docUrl}
					<LoadingSpinner class="my-auto text-secondary" />
				{:then docUrl}
					{#if docUrl}
						<PdfViewer
							{docUrl}
							previewChunk={showReferences.preview}
							previewPage={showReferences.preview.page ?? undefined}
						/>
					{/if}
				{/await}
			{/if}
		</div>
	</div>
</div>
