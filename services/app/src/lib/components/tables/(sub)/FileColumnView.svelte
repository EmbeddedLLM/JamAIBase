<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import ArrowDownToLine from 'lucide-svelte/icons/arrow-down-to-line';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Maximize2 from 'lucide-svelte/icons/maximize-2';
	import { fileColumnFiletypes } from '$lib/constants';
	import { isValidUri } from '$lib/utils';
	import logger from '$lib/logger';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let rowID: string | undefined = undefined;
	export let columnID: string;
	export let fileUri: string;
	export let fileUrl: string;
	export let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null;

	async function getRawFile() {
		if (!fileUri) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/files/url/raw`, {
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
			window.open(
				responseBody.urls[0]?.replace(new URL(responseBody.urls[0]).origin, ''),
				'_blank'
			);
		} else {
			if (response.status !== 404) {
				logger.error(toUpper(`${tableType}TBL_ROW_GETRAW`), responseBody);
			}
			toast.error('Failed to get raw file', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}
</script>

{#if fileUri && isValidUri(fileUri)}
	{@const fileType = fileColumnFiletypes.find(({ ext }) => fileUri.endsWith(ext))?.type}
	<div
		class="relative flex items-center justify-center {!fileUrl ||
		!isValidUri(fileUrl)?.protocol.startsWith('http')
			? 'h-full'
			: ''} w-full group/image"
	>
		{#if fileUrl && isValidUri(fileUrl)?.protocol.startsWith('http') && fileType !== undefined}
			{#if fileType === 'file'}
				<img
					src={fileUrl?.replace(new URL(fileUrl).origin, '')}
					alt=""
					class="z-0 h-[83px] sm:h-[133px] max-w-full object-contain"
				/>
			{:else if fileType === 'audio'}
				<audio controls src={fileUrl?.replace(new URL(fileUrl).origin, '')}></audio>
			{/if}
		{:else}
			<div class="flex items-center justify-center h-full">
				<div class="flex items-center gap-1 pl-1 pr-1.5 py-0.5 bg-white rounded">
					<DocumentFilledIcon
						class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					{fileUri.split('/').pop()}
				</div>
			</div>
		{/if}

		<div
			class="absolute top-0 right-0 flex gap-1 opacity-0 group-hover/image:opacity-100 group-focus-within/image:opacity-100 transition-opacity"
		>
			<Button
				variant="ghost"
				title="Delete file"
				on:click={() => (isDeletingFile = { rowID: rowID ?? '', columnID, fileUri })}
				class="p-0 h-6 text-[#F04438] hover:text-[#F04438] bg-white rounded-md aspect-square"
			>
				<Trash2 class="h-3.5 w-3.5" />
			</Button>

			{#if fileUrl && isValidUri(fileUrl)?.protocol.startsWith('http') && fileType === 'file'}
				<DropdownMenu.Root>
					<DropdownMenu.Trigger asChild let:builder>
						<Button
							builders={[builder]}
							variant="ghost"
							title="Enlarge file"
							class="p-0 h-6 text-[#667085] hover:text-[#667085] bg-white rounded-md aspect-square"
						>
							<Maximize2 class="h-3.5 w-3.5" />
						</Button>
					</DropdownMenu.Trigger>
					<DropdownMenu.Content
						data-testid="file-preview"
						class="flex flex-col gap-2 p-2 rounded-lg"
					>
						<div class="flex items-center justify-between">
							<span
								title={fileUri.split('/').pop()}
								class="px-1.5 max-w-[40vh] text-[#475467] bg-[#F9FAFB] line-clamp-1 rounded"
							>
								{fileUri.split('/').pop()}
							</span>
						</div>
						<img
							src={fileUrl?.replace(new URL(fileUrl).origin, '')}
							alt=""
							class="max-h-[40vh] max-w-[40vh] object-contain"
						/>
						<div class="flex items-center justify-end gap-1">
							<DropdownMenu.Item asChild let:builder>
								<Button
									builders={[builder]}
									variant="ghost"
									title="Download file"
									on:click={getRawFile}
									class="p-0 h-7 text-[#667085] hover:text-[#667085] bg-white border border-[#F2F4F7] rounded-md aspect-square shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)]"
								>
									<ArrowDownToLine class="h-4 w-4" />
								</Button>
							</DropdownMenu.Item>
							<DropdownMenu.Item asChild let:builder>
								<Button
									builders={[builder]}
									variant="ghost"
									title="Delete file"
									on:click={() => (isDeletingFile = { rowID: rowID ?? '', columnID, fileUri })}
									class="p-0 h-7 text-[#F04438] hover:text-[#F04438] bg-white border border-[#F2F4F7] rounded-md aspect-square shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)]"
								>
									<Trash2 class="h-4 w-4" />
								</Button>
							</DropdownMenu.Item>
						</div>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			{:else if fileUri}
				<Button
					variant="ghost"
					title="Download file"
					on:click={getRawFile}
					class="p-0 h-6 text-[#667085] hover:text-[#667085] bg-white border border-[#F2F4F7] rounded-md aspect-square shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)]"
				>
					<ArrowDownToLine class="h-3.5 w-3.5" />
				</Button>
			{/if}
		</div>
	</div>
{:else}
	<span class="h-min text-text">
		{fileUri === undefined ? null : fileUri}
	</span>
{/if}
