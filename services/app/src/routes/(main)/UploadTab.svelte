<script lang="ts">
	import { uploadQueue, uploadController } from '$globalStore';
	import type { UploadQueue } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import ArrowDownIcon from '$lib/icons/ArrowDownIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

	interface Props {
		completedUploads: UploadQueue['queue'];
	}

	let { completedUploads = $bindable() }: Props = $props();

	let uploadTabOpen = $state(true);
	let cancelUploadOpen = $state(false);

	let uploadTabEl: HTMLDivElement | undefined = $state();
	let isMovingTab = $state(false);
	let grabPosX = 0;

	let totalProgress = $derived(
		(completedUploads.length * 100) /
			($uploadQueue.queue.length + completedUploads.length + ($uploadQueue?.activeFile ? 1 : 0))
	);

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
			if (!uploadTabEl) return;
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
	onresize={() => {
		if (uploadTabEl) uploadTabEl.style.right = '';
	}}
/>
<svelte:document
	onmousemove={handleMoveTab}
	ontouchmove={handleMoveTab}
	onmouseup={() => {
		document.body.style.userSelect = 'unset';
		isMovingTab = false;
	}}
	ontouchend={() => {
		document.body.style.userSelect = 'unset';
		isMovingTab = false;
	}}
/>

{#if completedUploads.length || $uploadQueue.queue.length || $uploadQueue.activeFile}
	<div
		bind:this={uploadTabEl}
		id="upload-tab-global"
		class="fixed bottom-0 right-1/2 z-[20] flex h-[20rem] w-[clamp(0px,25rem,100%)] translate-x-1/2 flex-col rounded-t-lg bg-white shadow-[0px_-1px_10px_0px] shadow-black/25 data-dark:bg-[#42464e] sm:right-12 sm:translate-x-0 sm:rounded-t-xl {!uploadTabOpen &&
			'translate-y-[calc(20rem_-_45px)] sm:translate-y-[calc(20rem_-_57px)]'} transition-transform duration-300"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			onmousedown={handleGrabTab}
			ontouchstart={handleGrabTab}
			class="flex cursor-move items-center justify-between py-1 pl-6 pr-3 sm:py-2"
		>
			<h3 class="text-sm font-medium sm:text-base">
				Uploaded {completedUploads.length} of {$uploadQueue.queue.length +
					completedUploads.length +
					($uploadQueue?.activeFile ? 1 : 0)} file(s)
			</h3>

			<div class="flex items-center gap-1">
				<Button
					variant="ghost"
					aria-label="Minimize uploads"
					onclick={() => (uploadTabOpen = !uploadTabOpen)}
					class="aspect-square h-8 rounded-full p-0 sm:h-9"
				>
					<ArrowDownIcon
						class="w-5 sm:w-6 {!uploadTabOpen &&
							'rotate-180'} pointer-events-none transition-transform duration-300"
					/>
				</Button>

				<Button
					variant="ghost"
					aria-label="Close and cancel ongoing uploads"
					onclick={() => {
						if ($uploadQueue.queue.length || $uploadQueue.activeFile) {
							cancelUploadOpen = true;
						} else {
							completedUploads = [];
						}
					}}
					class="aspect-square h-8 rounded-full p-0 sm:h-9"
				>
					<CloseIcon class="pointer-events-none w-5 sm:w-6" />
				</Button>
			</div>
		</div>

		<progress
			value={totalProgress}
			max="100"
			class="total-progress relative h-[5px] w-full appearance-none overflow-hidden"
		></progress>

		<div role="list" class="flex grow flex-col overflow-auto bg-[#FCFCFC] data-dark:bg-[#202226]">
			{#each completedUploads as completedUpload}
				<div
					data-testid="complete-upload-file"
					role="listitem"
					class="border-b border-[#DDD] p-3 data-dark:border-[#454545]"
				>
					<div class="mb-1 flex items-center gap-2 px-1">
						<DocumentFilledIcon
							class="h-6 flex-[0_0_auto] [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={completedUpload.file.name} class="mr-auto line-clamp-1 break-all">
							{completedUpload.file.name}
						</span>
						<div
							class="flex flex-[0_0_auto] items-center justify-center rounded-full bg-[#2ECC40] p-1 data-dark:bg-[#54D362]"
						>
							<CheckIcon class="w-3 stroke-white stroke-[3] data-dark:stroke-black" />
						</div>
					</div>
					<p title={completedUpload.successText} class="line-clamp-1 break-all px-8 text-sm italic">
						{completedUpload.successText}
					</p>
				</div>
			{/each}
			{#if $uploadQueue.activeFile}
				<div
					data-testid="active-upload-file"
					role="listitem"
					class="border-b border-[#DDD] p-3 data-dark:border-[#454545]"
				>
					<div class="mb-1 flex items-center gap-2 px-1">
						<DocumentFilledIcon
							class="h-6 flex-[0_0_auto] [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={$uploadQueue.activeFile.file.name} class="mr-auto line-clamp-1 break-all">
							{$uploadQueue.activeFile.file.name}
						</span>
						<div
							class="radial-progress flex-[0_0_auto] text-secondary [transform:_scale(-1,_1)]"
							style="--value:{Math.floor($uploadQueue.progress)}; --size:20px; --thickness: 5px;"
						></div>
					</div>
					{#if $uploadQueue.progress === 100}
						<p class="px-1 pl-8 text-sm italic">{$uploadQueue.activeFile.completeText}</p>
					{:else}
						<p class="px-1 pl-8 text-sm italic">{$uploadQueue.progress}%</p>
					{/if}
				</div>
			{/if}
			{#each $uploadQueue.queue as queuedFile}
				<div
					data-testid="queued-upload-file"
					role="listitem"
					class="border-b border-[#DDD] px-3 py-4 data-dark:border-[#454545]"
				>
					<div class="flex items-center px-1">
						<DocumentFilledIcon
							class="h-6 flex-[0_0_auto] [&>path]:fill-[#8E4585] data-dark:[&>path]:fill-[#CB63BE]"
						/>
						<span title={queuedFile.file.name} class="ml-2 mr-auto line-clamp-1 break-all">
							{queuedFile.file.name}
						</span>
						<div class="flex flex-[0_0_auto] items-center justify-center">
							<span class="px-1 text-sm italic text-[#999999] data-dark:text-[#C9C9C9]">
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
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<div class="flex grow flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="text-2xl font-bold">Cancel Upload?</h3>
			<p class="text-sm text-text/60">
				The upload process appears to be unfinished. Do you wish to cancel the upload?
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] py-3 data-dark:bg-[#303338]">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Button variant="link" type="button" onclick={handleCancelUpload} class="grow px-6">
					Cancel Upload
				</Button>
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="destructive" type="button" class="grow px-6">
							Continue Upload
						</Button>
					{/snippet}
				</Dialog.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
