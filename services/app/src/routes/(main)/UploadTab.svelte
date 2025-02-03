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

	let uploadTabOpen = true;
	let cancelUploadOpen = false;

	let uploadTabEl: HTMLDivElement;
	let isMovingTab = false;
	let grabPosX = 0;

	$: totalProgress =
		(completedUploads.length * 100) /
		($uploadQueue.queue.length + completedUploads.length + ($uploadQueue?.activeFile ? 1 : 0));

	function handleCancelUpload() {
		$uploadController?.abort();
		$uploadQueue.queue = [];
		$uploadQueue.activeFile = null;
		$uploadQueue.progress = 0;
		completedUploads = [];
		cancelUploadOpen = false;
	}

	function handleGrabTab(e: MouseEvent | TouchEvent) {
		if ((e.target as HTMLElement).tagName == 'BUTTON') return;
		const rect = (e.target as HTMLElement)?.getBoundingClientRect();
		grabPosX = (e instanceof TouchEvent ? e.touches[0].clientX : e.clientX) - rect.left;
		isMovingTab = true;
	}

	let animationFrameId: ReturnType<typeof requestAnimationFrame> | null;
	function handleMoveTab(e: MouseEvent | TouchEvent) {
		if (!isMovingTab) return;

		if (animationFrameId) {
			cancelAnimationFrame(animationFrameId);
		}

		animationFrameId = requestAnimationFrame(() => {
			document.body.style.userSelect = 'none';

			const clientX = e instanceof TouchEvent ? e.touches[0].clientX : e.clientX;
			if (clientX <= grabPosX) {
				uploadTabEl.style.right = window.innerWidth - 400 + 'px';
			} else if (clientX + 400 - grabPosX > window.innerWidth) {
				uploadTabEl.style.right = '0px';
			} else {
				uploadTabEl.style.right = window.innerWidth - clientX - 400 + grabPosX + 'px';
			}

			animationFrameId = null;
		});
	}
</script>

<svelte:window
	on:resize={() => {
		if (uploadTabEl) uploadTabEl.style.right = '';
	}}
/>
<svelte:document
	on:mousemove={handleMoveTab}
	on:touchmove={handleMoveTab}
	on:mouseup={() => {
		document.body.style.userSelect = 'unset';
		isMovingTab = false;
	}}
	on:touchend={() => {
		document.body.style.userSelect = 'unset';
		isMovingTab = false;
	}}
/>

{#if completedUploads.length || $uploadQueue.queue.length || $uploadQueue.activeFile}
	<div
		bind:this={uploadTabEl}
		id="upload-tab-global"
		class="fixed z-[100] bottom-0 right-1/2 sm:right-12 translate-x-1/2 sm:translate-x-0 flex flex-col h-[20rem] w-[clamp(0px,25rem,100%)] bg-white data-dark:bg-[#42464e] rounded-t-lg sm:rounded-t-xl shadow-[0px_-1px_10px_0px] shadow-black/25 {!uploadTabOpen &&
			'translate-y-[calc(20rem_-_45px)] sm:translate-y-[calc(20rem_-_57px)]'} transition-transform duration-300"
	>
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div
			on:mousedown={handleGrabTab}
			on:touchstart={handleGrabTab}
			class="flex items-center justify-between pl-6 pr-3 py-1 sm:py-2 cursor-move"
		>
			<h3 class="font-medium text-sm sm:text-base">
				Uploaded {completedUploads.length} of {$uploadQueue.queue.length +
					completedUploads.length +
					($uploadQueue?.activeFile ? 1 : 0)} file(s)
			</h3>

			<div class="flex items-center gap-1">
				<Button
					variant="ghost"
					aria-label="Minimize uploads"
					on:click={() => (uploadTabOpen = !uploadTabOpen)}
					class="p-0 h-8 sm:h-9 aspect-square rounded-full"
				>
					<ArrowDownIcon
						class="w-5 sm:w-6 {!uploadTabOpen &&
							'rotate-180'} transition-transform duration-300 pointer-events-none"
					/>
				</Button>

				<Button
					variant="ghost"
					aria-label="Close and cancel ongoing uploads"
					on:click={() => {
						if ($uploadQueue.queue.length || $uploadQueue.activeFile) {
							cancelUploadOpen = true;
						} else {
							completedUploads = [];
						}
					}}
					class="p-0 h-8 sm:h-9 aspect-square rounded-full"
				>
					<CloseIcon class="w-5 sm:w-6 pointer-events-none" />
				</Button>
			</div>
		</div>

		<progress
			value={totalProgress}
			max="100"
			class="total-progress relative h-[5px] w-full appearance-none overflow-hidden"
		></progress>

		<div role="list" class="grow flex flex-col overflow-auto bg-[#FCFCFC] data-dark:bg-[#202226]">
			{#each completedUploads as completedUpload}
				<div
					data-testid="complete-upload-file"
					role="listitem"
					class="p-3 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center gap-2 mb-1 px-1">
						<DocumentFilledIcon
							class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={completedUpload.file.name} class="mr-auto line-clamp-1 break-all">
							{completedUpload.file.name}
						</span>
						<div
							class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
						>
							<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
						</div>
					</div>
					<p title={completedUpload.successText} class="text-sm italic px-8 line-clamp-1 break-all">
						{completedUpload.successText}
					</p>
				</div>
			{/each}
			{#if $uploadQueue.activeFile}
				<div
					data-testid="active-upload-file"
					role="listitem"
					class="p-3 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center gap-2 mb-1 px-1">
						<DocumentFilledIcon
							class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={$uploadQueue.activeFile.file.name} class="mr-auto line-clamp-1 break-all">
							{$uploadQueue.activeFile.file.name}
						</span>
						<div
							class="flex-[0_0_auto] radial-progress text-secondary [transform:_scale(-1,_1)]"
							style="--value:{Math.floor($uploadQueue.progress)}; --size:20px; --thickness: 5px;"
						></div>
					</div>
					{#if $uploadQueue.progress === 100}
						<p class="text-sm italic px-1 pl-8">{$uploadQueue.activeFile.completeText}</p>
					{:else}
						<p class="text-sm italic px-1 pl-8">{$uploadQueue.progress}%</p>
					{/if}
				</div>
			{/if}
			{#each $uploadQueue.queue as queuedFile}
				<div
					data-testid="queued-upload-file"
					role="listitem"
					class="px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]"
				>
					<div class="flex items-center px-1">
						<DocumentFilledIcon
							class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={queuedFile.file.name} class="ml-2 mr-auto line-clamp-1 break-all">
							{queuedFile.file.name}
						</span>
						<div class="flex-[0_0_auto] flex items-center justify-center">
							<span class="px-1 text-sm text-[#999999] data-dark:text-[#C9C9C9] italic">
								Queued
							</span>
						</div>
					</div>
				</div>
			{/each}

			<!-- !TEST ELEMENTS -->
			<!-- <div class="p-3 border-b border-[#DDD] data-dark:border-[#454545]">
				<div class="flex items-center gap-2 mb-1 px-1">
					<DocumentFilledIcon
						class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span title="test-file-uploading.jpg" class="mr-auto line-clamp-1 break-all">
						test-file-uploading.jpg
					</span>
					<div
						class="flex-[0_0_auto] radial-progress text-secondary [transform:_scale(-1,_1)]"
						style="--value:{Math.floor(50)}; --size:20px; --thickness: 5px;"
					/>
				</div>
				{#if $uploadQueue.progress === 100}
					<p class="text-sm italic px-1 pl-8">Embedding file...</p>
				{:else}
					<p class="text-sm italic px-1 pl-8">50%</p>
				{/if}
			</div>

			<div class="p-3 border-b border-[#DDD] data-dark:border-[#454545]">
				<div class="flex items-center gap-2 mb-1 px-1">
					<DocumentFilledIcon
						class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span title="test-file-uploaded.jpg" class="mr-auto line-clamp-1 break-all">
						test-file-uploaded.jpg
					</span>
					<div
						class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
					>
						<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
					</div>
				</div>
				<p title="test-table" class="text-sm italic px-8 line-clamp-1 break-all">
					Uploaded to table: test-table
				</p>
			</div>

			<div class="px-3 py-4 border-b border-[#DDD] data-dark:border-[#454545]">
				<div class="flex items-center px-1">
					<DocumentFilledIcon
						class="flex-[0_0_auto] h-6 [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
					/>
					<span title="test-file-queued.jpg" class="ml-2 mr-auto line-clamp-1 break-all">
						test-file-queued.jpg
					</span>
					<div class="flex-[0_0_auto] flex items-center justify-center">
						<span class="px-1 text-sm text-[#999999] data-dark:text-[#C9C9C9] italic">Queued</span>
					</div>
				</div>
			</div> -->
		</div>
	</div>
{/if}

<Dialog.Root bind:open={cancelUploadOpen}>
	<Dialog.Content class="h-[17rem] w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]">
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
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Button variant="link" type="button" on:click={handleCancelUpload} class="grow px-6">
					Cancel Upload
				</Button>
				<DialogPrimitive.Close asChild let:builder>
					<Button
						builders={[builder]}
						variant="destructive"
						type="button"
						class="grow px-6 rounded-full"
					>
						Continue Upload
					</Button>
				</DialogPrimitive.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
