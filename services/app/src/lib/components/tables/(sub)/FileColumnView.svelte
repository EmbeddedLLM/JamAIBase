<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import ArrowDownToLine from 'lucide-svelte/icons/arrow-down-to-line';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Maximize2 from 'lucide-svelte/icons/maximize-2';
	import { fileColumnFiletypes } from '$lib/constants';
	import { isValidUri } from '$lib/utils';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		readonly?: boolean;
		rowID?: string | undefined;
		columnID: string;
		fileUri: string;
		fileUrl: string;
		isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null;
	}

	let {
		tableType,
		readonly,
		rowID = undefined,
		columnID,
		fileUri,
		fileUrl,
		isDeletingFile = $bindable()
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
		class="relative flex items-center justify-center {!fileUrl ||
		!isValidUri(fileUrl)?.protocol.startsWith('http') ||
		// fix for inconsistent thumbs gen
		fileType === 'document'
			? 'h-full'
			: ''} group/image w-full p-2"
	>
		{#if fileUrl && isValidUri(fileUrl)?.protocol.startsWith('http') && fileType !== undefined}
			{#if fileType === 'image'}
				<img src={fileUrl} alt="" class="z-0 h-[83px] max-w-full object-contain sm:h-[133px]" />
			{:else if fileType === 'audio'}
				<audio controls src={fileUrl}></audio>
			{:else if fileType === 'document'}
				<div class="flex h-full items-center justify-center">
					<div class="flex items-center gap-1.5 rounded bg-white py-1 pl-1 pr-1.5">
						<img src={fileUrl} alt="" class="z-0 h-5 max-w-full object-contain" />
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
					onclick={() => (isDeletingFile = { rowID: rowID ?? '', columnID, fileUri })}
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

			{#if fileUrl && isValidUri(fileUrl)?.protocol.startsWith('http') && fileType === 'image'}
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button
								{...props}
								variant="ghost"
								title="Enlarge file"
								class="aspect-square h-6 rounded-md bg-white p-0 text-[#667085] hover:text-[#667085]"
							>
								<Maximize2 class="h-3.5 w-3.5" />
							</Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content
						data-testid="file-preview"
						class="z-[49] flex flex-col gap-2 rounded-lg p-2"
					>
						<div class="flex items-center justify-between overflow-auto">
							<span
								title={fileUri.split('/').pop()}
								class="line-clamp-1 max-w-[45vw] break-all rounded bg-[#F2F4F7] px-1.5 text-[#475467]"
							>
								{fileUri.split('/').pop()}
							</span>
						</div>
						<img src={fileUrl} alt="" class="max-h-[45vh] w-[45vw] max-w-[45vw] object-contain" />
						<div class="flex items-center justify-end gap-1">
							<DropdownMenu.Item>
								{#snippet child({ props })}
									<Button
										{...props}
										variant="ghost"
										title="Download file"
										onclick={() => getRawFile(fileUri)}
										class="aspect-square h-7 rounded-md border border-[#F2F4F7] bg-white p-0 text-[#667085] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:text-[#667085]"
									>
										<ArrowDownToLine class="h-4 w-4" />
									</Button>
								{/snippet}
							</DropdownMenu.Item>
							{#if !readonly}
								<DropdownMenu.Item>
									{#snippet child({ props })}
										<Button
											{...props}
											variant="ghost"
											title="Delete file"
											onclick={() => (isDeletingFile = { rowID: rowID ?? '', columnID, fileUri })}
											class="aspect-square h-7 rounded-md border border-[#F2F4F7] bg-white p-0 text-[#F04438] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:text-[#F04438]"
										>
											<Trash2 class="h-4 w-4" />
										</Button>
									{/snippet}
								</DropdownMenu.Item>
							{/if}
						</div>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			{/if}
		</div>
	</div>
{:else}
	<span class="h-min text-text">
		{fileUri === undefined ? null : fileUri}
	</span>
{/if}
