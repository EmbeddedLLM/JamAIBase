<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { uploadQueue, uploadController } from '$globalStore';
	import type { UploadQueue } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import ArrowDownIcon from '$lib/icons/ArrowDownIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

	export let completedUploads: UploadQueue['queue'];

	let uploadTabOpen = false;
	let cancelUploadOpen = false;

	let uploadTabEl: HTMLDivElement;
	let isMovingTab = false;
	let grabPosX = 0;

	function handleCancelUpload() {
		$uploadController?.abort();
		$uploadQueue.queue = [];
		$uploadQueue.activeFile = null;
		$uploadQueue.progress = 0;
		completedUploads = [];
		cancelUploadOpen = false;
	}

	function handleGrabTab(e: MouseEvent) {
		if ((e.target as HTMLElement).tagName == 'BUTTON') return;
		const rect = (e.target as HTMLElement)?.getBoundingClientRect();
		grabPosX = e.clientX - rect.left;
		isMovingTab = true;
	}

	function handleMoveTab(e: MouseEvent) {
		if (!isMovingTab) return;

		document.body.style.userSelect = 'none';

		if (e.clientX <= grabPosX) {
			uploadTabEl.style.right = window.innerWidth - 400 + 'px';
		} else if (e.clientX + 400 - grabPosX > window.innerWidth) {
			uploadTabEl.style.right = '0px';
		} else {
			uploadTabEl.style.right = window.innerWidth - e.clientX - 400 + grabPosX + 'px';
		}
	}
</script>

<svelte:window
	on:resize={() => {
		if (uploadTabEl) uploadTabEl.style.right = '';
	}}
/>
<svelte:document
	on:mousemove={handleMoveTab}
	on:mouseup={() => {
		document.body.style.userSelect = 'unset';
		isMovingTab = false;
	}}
/>

{#if completedUploads.length || $uploadQueue.queue.length || $uploadQueue.activeFile}
	<div
		bind:this={uploadTabEl}
		class={`absolute z-[100] bottom-0 right-12 flex flex-col h-[17rem] w-[25rem] bg-white data-dark:bg-[#42464e] rounded-t-xl shadow-[0px_-1px_10px_0px] shadow-black/25 ${
			!uploadTabOpen && 'translate-y-[211px]'
		} transition-transform duration-300`}
	>
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div
			on:mousedown={handleGrabTab}
			class="flex items-center justify-between pl-6 pr-3 py-2 cursor-move"
		>
			<h3 class="font-medium">
				{#if $uploadQueue.activeFile}
					Uploading {$uploadQueue.queue.length + 1} file(s)... ({$uploadQueue.progress}%)
				{:else}
					Upload complete (100%)
				{/if}
			</h3>

			<div class="flex items-center gap-1">
				<Button
					variant="ghost"
					on:click={() => (uploadTabOpen = !uploadTabOpen)}
					class="p-0 aspect-square rounded-full"
				>
					<ArrowDownIcon
						class={`w-6 ${
							!uploadTabOpen && 'rotate-180'
						} transition-transform duration-300 pointer-events-none`}
					/>
				</Button>

				<Button
					variant="ghost"
					on:click={() => {
						if ($uploadQueue.queue.length || $uploadQueue.activeFile) {
							cancelUploadOpen = true;
						} else {
							completedUploads = [];
						}
					}}
					class="p-0 aspect-square rounded-full"
				>
					<CloseIcon class="w-6 pointer-events-none" />
				</Button>
			</div>
		</div>

		<progress
			value={$uploadQueue.progress}
			max="100"
			class="total-progress relative h-[5px] w-full appearance-none overflow-hidden"
		/>

		<div class="grow flex flex-col overflow-auto bg-[#FCFCFC] data-dark:bg-[#202226]">
			{#each completedUploads as completedUpload}
				<div
					class="flex items-center justify-between px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center justify-between gap-2 px-1">
						<DocumentFilledIcon
							class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={completedUpload.file.name} class="line-clamp-1"
							>{completedUpload.file.name}</span
						>
					</div>
					<div
						class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
					>
						<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
					</div>
				</div>
			{/each}
			{#if $uploadQueue.activeFile}
				<div
					class="flex items-center justify-between px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center justify-between gap-2 px-1">
						<DocumentFilledIcon
							class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={$uploadQueue.activeFile.name} class="line-clamp-1">
							{$uploadQueue.activeFile.name}
						</span>
					</div>
					<div
						class="flex-[0_0_auto] radial-progress text-[#30A8FF] [transform:_scale(-1,_1)]"
						style={`--value:${Math.floor($uploadQueue.progress)}; --size:1.3rem; --thickness: 5px;`}
					/>
				</div>
			{/if}
			{#each $uploadQueue.queue as queuedFile}
				<div
					class="flex items-center justify-between px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center justify-between gap-2 px-1">
						<DocumentFilledIcon
							class="h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={queuedFile.file.name} class="line-clamp-1">{queuedFile.file.name}</span>
					</div>
					<span class="px-1 text-sm text-[#999999] data-dark:text-[#C9C9C9] italic">Queued</span>
				</div>
			{/each}

			<!-- !TEST ELEMENTS -->
			<!-- <div
				class="flex items-center justify-between px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
			>
				<div class="flex items-center justify-between gap-2 px-1">
					<DocumentFilledIcon
						class="h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span title="test-file-uploading.jpg" class="line-clamp-1">
						test-file-uploading.jpg
					</span>
				</div>
				<div
					class="radial-progress text-[#30A8FF] [transform:_scale(-1,_1)]"
					style={`--value:${Math.floor(23)}; --size:1.3rem; --thickness: 5px;`}
				/>
			</div>

			<div
				class="flex items-center justify-between px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
			>
				<div class="flex items-center justify-between gap-2 px-1">
					<DocumentFilledIcon
						class="h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span title="test-file-queued.jpg" class="line-clamp-1">test-file-queued.jpg</span>
				</div>
				<span class="px-1 text-sm text-[#999999] data-dark:text-[#C9C9C9] italic">Queued</span>
			</div> -->
		</div>
	</div>
{/if}

<Dialog.Root bind:open={cancelUploadOpen}>
	<Dialog.Content class="h-[17rem] w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="grow flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Cancel Upload?</h3>
			<p class="text-text/60 text-sm">
				The upload process appears to be unfinished. Do you wish to cancel the upload?
			</p>
		</div>

		<Dialog.Actions class="py-3 bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2">
				<Button variant="link" on:click={handleCancelUpload} class="grow px-6">
					Cancel Upload
				</Button>
				<Button
					variant="destructive"
					on:click={() => (cancelUploadOpen = false)}
					class="grow px-6 rounded-full"
				>
					Continue Upload
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
