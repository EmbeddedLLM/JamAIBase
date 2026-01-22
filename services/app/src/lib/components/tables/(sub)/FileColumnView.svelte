<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import ArrowDownToLine from 'lucide-svelte/icons/arrow-down-to-line';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Maximize2 from 'lucide-svelte/icons/maximize-2';
	import { getTableState } from '$lib/components/tables/tablesState.svelte';
	import { fileColumnFiletypes } from '$lib/constants';
	import { isValidUri } from '$lib/utils';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';

	const tableState = getTableState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		readonly?: boolean;
		rowID?: string | undefined;
		columnID: string;
		fileUri: string;
		fileThumb: { value: string; url: string } | undefined;
		deletingFile?: { rowID: string; columnID: string; fileUri?: string } | null;
	}

	let {
		tableType,
		readonly,
		rowID = undefined,
		columnID,
		fileUri,
		fileThumb,
		deletingFile = $bindable()
	}: Props = $props();

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

{#if fileUri && isValidUri(fileUri)}
	{@const fileType = fileColumnFiletypes.find(({ ext }) =>
		fileUri.toLowerCase().endsWith(ext)
	)?.type}
	<div
		class="relative flex items-center justify-center {!fileThumb ||
		!isValidUri(fileThumb.url)?.protocol.startsWith('http') ||
		// fix for inconsistent thumbs gen
		fileType === 'document'
			? 'h-full'
			: ''} group/image w-full p-2"
	>
		{#if fileThumb && isValidUri(fileThumb.url)?.protocol.startsWith('http') && fileUri === fileThumb.value && fileType !== undefined}
			{#if fileType === 'image'}
				<img
					src={fileThumb.url}
					alt=""
					class="z-0 h-[83px] max-w-full object-contain sm:h-[133px]"
				/>
			{:else if fileType === 'audio'}
				<audio controls src={fileThumb.url}></audio>
			{:else if fileType === 'document'}
				<div class="flex h-full items-center justify-center">
					<div class="flex items-center gap-1.5 rounded bg-white py-1 pl-1 pr-1.5">
						<img src={fileThumb.url} alt="" class="z-0 h-5 max-w-full object-contain" />
						{fileUri.split('/').pop()}
					</div>
				</div>
			{/if}
		{:else}
			<div class="flex h-full items-center justify-center">
				<div class="flex items-center gap-1 rounded bg-white py-0.5 pl-1 pr-1.5">
					<DocumentFilledIcon
						class="h-6 flex-[0_0_auto] [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span class="break-all">
						{fileUri.split('/').pop()}
					</span>
				</div>
			</div>
		{/if}

		<div
			class="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-focus-within/image:opacity-100 group-hover/image:opacity-100"
		>
			{#if !readonly}
				<Button
					variant="ghost"
					title="Delete file"
					onclick={() => {
						if (deletingFile === undefined) {
							tableState.deletingFile = { rowID: rowID ?? '', columnID, fileUri };
						} else {
							deletingFile = { rowID: rowID ?? '', columnID, fileUri };
						}
					}}
					class="aspect-square h-6 rounded-md bg-white p-0 text-[#F04438] hover:text-[#F04438]"
				>
					<Trash2 class="h-3.5 w-3.5" />
				</Button>
			{/if}

			<Button
				variant="ghost"
				title="Download file"
				onclick={() => getRawFile(fileUri)}
				class="aspect-square h-6 rounded-md bg-white p-0 text-[#667085] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:text-[#667085]"
			>
				<ArrowDownToLine class="h-3.5 w-3.5" />
			</Button>

			{#if fileThumb && isValidUri(fileThumb.url)?.protocol.startsWith('http') && fileType === 'image'}
				<Button
					variant="ghost"
					title="Enlarge file"
					onclick={() => {
						tableState.showOutputDetails = {
							open: true,
							activeCell: { rowID: rowID ?? '', columnID },
							activeTab: 'image',
							message: {
								content: fileUri,
								error: null,
								chunks: [],
								fileUrl: fileThumb.url
							},
							reasoningContent: null,
							reasoningTime: null,
							expandChunk: null,
							preview: null
						};
					}}
					class="aspect-square h-6 rounded-md bg-white p-0 text-[#667085] hover:text-[#667085]"
				>
					<Maximize2 class="h-3.5 w-3.5" />
				</Button>
			{/if}
		</div>
	</div>
{:else}
	<span class="h-min text-text">
		{fileUri === undefined ? null : fileUri}
	</span>
{/if}
