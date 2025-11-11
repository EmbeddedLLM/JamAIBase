<script lang="ts">
	import { ArrowDownToLine, AudioLines } from '@lucide/svelte';
	import { fileColumnFiletypes } from '$lib/constants';
	import { chatState } from '../../../chat.svelte';

	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	let {
		showChatControls = $bindable(),
		showRawTexts = $bindable(),
		showFilePreview = $bindable(),
		rowThumbs,
		getRawFile
	}: {
		showChatControls: { open: boolean; value: string | null };
		showRawTexts: boolean;
		showFilePreview: string | null;
		rowThumbs: { [uri: string]: string };
		getRawFile: (fileUri: string) => Promise<void>;
	} = $props();
</script>

<div class="z-[1] pb-4 pl-2 pr-3">
	<div
		style="box-shadow: 0px 2px 4px 0px rgba(0, 0, 0, 0.08);"
		class="flex h-full flex-col rounded-lg border border-[#E4E7EC] bg-white"
	>
		<div
			class="relative flex h-min items-center justify-between space-y-1.5 rounded-t-lg bg-white px-4 py-3 text-left text-lg font-medium text-[#344054] data-dark:bg-[#303338]"
		>
			Chat controls

			<button
				onclick={() => (showChatControls = { ...showChatControls, open: false })}
				class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
			>
				<CloseIcon class="w-6" />
				<span class="sr-only">Close</span>
			</button>
		</div>

		<div class="flex h-1 grow flex-col gap-4 overflow-auto px-1 pb-1">
			<div class="flex flex-col gap-1 px-3">
				<span class="text-sm font-medium uppercase text-[#98A2B3]">Agent name</span>

				<InputText
					readonly
					value={chatState.conversation?.parent_id ?? ''}
					class="h-9 rounded-md bg-[#F2F4F7] pl-8 text-[#344054] transition-opacity placeholder:not-italic placeholder:text-[#98A2B3]"
				>
					{#snippet leading()}
						<ChatAgentIcon
							class="pointer-events-none absolute left-2 top-1/2 h-5 -translate-y-[40%] text-[#667085] transition-opacity"
						/>
					{/snippet}
				</InputText>
			</div>

			<div class="flex flex-col gap-1 px-3">
				<span class="text-sm font-medium uppercase text-[#98A2B3]">Chat view</span>

				<div
					style="grid-template-columns: repeat(2, minmax(5rem, 1fr));"
					class="relative grid w-full place-items-center rounded-lg bg-[#E4E7EC] p-0.5 text-sm after:pointer-events-none after:absolute after:left-0.5 after:top-1/2 after:z-0 after:h-[calc(100%_-_4px)] after:w-1/2 after:-translate-y-1/2 after:rounded-lg after:bg-white after:transition-transform after:duration-200 after:content-[''] data-dark:bg-gray-700 {!showRawTexts
						? 'after:translate-x-0'
						: 'after:translate-x-[calc(100%_-_4px)]'}"
				>
					<button
						onclick={() => (showRawTexts = false)}
						class="z-10 w-full rounded-lg px-2 py-1 transition-colors ease-in-out {!showRawTexts
							? 'text-[#667085]'
							: 'text-[#98A2B3]'}"
					>
						Simplified
					</button>

					<button
						onclick={() => (showRawTexts = true)}
						class="z-10 w-full rounded-lg px-2 py-1 transition-colors ease-in-out {showRawTexts
							? 'text-[#667085]'
							: 'text-[#98A2B3]'}"
					>
						Default
					</button>
				</div>
			</div>

			<div class="flex flex-col gap-1 px-3">
				<span class="text-sm font-medium uppercase text-[#98A2B3]">Media & files</span>

				<ul class="flex flex-wrap gap-1">
					{#each Object.entries(rowThumbs) as [uri, url]}
						{@const fileType = fileColumnFiletypes.find(({ ext }) =>
							uri.toLowerCase().endsWith(ext)
						)?.type}
						{@const fileUrl = rowThumbs[uri]}
						<div class="group/image relative">
							<button
								title={uri.split('/').pop()}
								onclick={() => (showFilePreview = uri)}
								class="flex h-36 w-36 items-center justify-center overflow-hidden rounded-xl bg-[#BF416E]"
							>
								{#if fileType === 'image'}
									<img src={fileUrl} alt="" class="z-0 h-full w-full object-cover" />
								{:else if fileType === 'audio'}
									<AudioLines class="h-16 w-16 text-white" />
								{:else if fileType === 'document'}
									<img src={fileUrl} alt="" class="z-0 max-w-full object-contain" />
								{/if}
							</button>

							<div
								class="absolute right-1 top-1 flex gap-1 opacity-0 transition-opacity group-focus-within/image:opacity-100 group-hover/image:opacity-100"
							>
								<Button
									variant="ghost"
									title="Download file"
									onclick={() => getRawFile(uri)}
									class="aspect-square h-6 rounded-md border border-[#F2F4F7] bg-white p-0 text-[#667085] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:text-[#667085]"
								>
									<ArrowDownToLine class="h-3.5 w-3.5" />
								</Button>
							</div>
						</div>
					{/each}
				</ul>
			</div>
		</div>
	</div>
</div>
