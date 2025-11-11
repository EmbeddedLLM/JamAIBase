<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import * as PDFObject from 'pdfobject';
	import csv from 'csvtojson';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../showdown-theme.css';
	import { codeblock, codehighlight, table as tableExtension } from '$lib/showdown';
	import { AudioLines } from '@lucide/svelte';
	import logger from '$lib/logger';
	import { fileColumnFiletypes } from '$lib/constants';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Dialog from '$lib/components/ui/dialog';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	let { showFilePreview = $bindable() }: { showFilePreview: string | null } = $props();

	let fileUrl = $state<string | null>(null);

	async function getRawFile() {
		if (!showFilePreview) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/raw`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				uris: [showFilePreview]
			})
		});
		const responseBody = await response.json();

		if (response.ok) {
			fileUrl = responseBody.urls[0];
		} else {
			if (response.status !== 404) {
				logger.error('CHAT_FILE_GETRAW', responseBody);
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

	const converter = new showdown.Converter({
		tables: true,
		tasklists: true,
		disableForced4SpacesIndentedSublists: true,
		strikethrough: true,
		ghCompatibleHeaderId: true,
		extensions: [showdownHtmlEscape, codeblock, codehighlight, tableExtension]
	});

	async function loadPreview() {
		if (!fileUrl) return;
		const response = await fetch(fileUrl);

		const responseBody = await response.text();
		if (response.status != 200) {
			logger.error('FILES_PREVIEW_FAILED', responseBody);
			console.error(responseBody);
			throw new Error(responseBody);
		}

		if (showFilePreview?.toLowerCase()?.endsWith('.csv')) {
			return await parseCsv(responseBody);
		} else {
			return responseBody;
		}
	}

	async function parseCsv(csvStr: string) {
		const csvRows: string[][] = [];
		await csv({ noheader: true, output: 'csv' })
			.fromString(csvStr)
			.then((csvRow) => {
				csvRows.push(csvRow);
			});

		return csvRows;
	}

	$effect(() => {
		if (!showFilePreview) {
			fileUrl = null;
		} else {
			getRawFile();
		}
	});

	let embedTimeout: ReturnType<typeof setTimeout>;
	$effect(() => {
		if (fileUrl) {
			embedTimeout = setTimeout(async () => {
				if (!['txt', 'md', 'csv'].includes(showFilePreview?.split('.').pop() ?? '')) {
					const isFileExists = await fetch(fileUrl!).then(
						(res) => res.status != 404 && res.status != 403
					);

					if (isFileExists) {
						PDFObject.embed(fileUrl!, '#preview1');
					}
				}
			}, 100);
		}
	});

	$effect(() => {
		if (!showFilePreview) {
			clearTimeout(embedTimeout);
		}
	});
</script>

<Dialog.Root bind:open={() => !!showFilePreview, () => (showFilePreview = null)}>
	{@const fileType = fileColumnFiletypes.find(({ ext }) =>
		showFilePreview?.toLowerCase().endsWith(ext)
	)?.type}
	<Dialog.Content
		class="max-h-[85vh] max-w-[85vw] shadow-[unset] {fileType === 'document'
			? 'h-[85vh] w-[clamp(0px,50rem,100%)]'
			: 'w-auto bg-[unset]'}"
	>
		{#if fileUrl}
			{#if fileType === 'image'}
				<img src={fileUrl} alt="" class="z-0 h-full w-full object-contain" />
			{:else if fileType === 'audio'}
				<div class="flex flex-col gap-2 rounded-xl bg-black p-4">
					<div class="flex h-64 items-center justify-center rounded-xl bg-[#BF416E]">
						<AudioLines class="h-20 w-20 text-white" />
					</div>
					<span class="line-clamp-1 text-white">{showFilePreview?.split('/').pop()}</span>
					<audio controls src={fileUrl} class="rounded-lg"></audio>
				</div>
			{:else if fileType === 'document'}
				<Dialog.Header>{showFilePreview?.split('/').pop() ?? 'File preview'}</Dialog.Header>
				<div class="flex w-full grow flex-col overflow-auto">
					{#if showFilePreview?.toLowerCase()?.endsWith('.txt')}
						{#await loadPreview() then previewContent}
							<div class="z-10 h-full w-full">
								<p class="h-full w-full overflow-auto whitespace-pre-wrap p-2 text-sm text-black">
									{previewContent}
								</p>
							</div>
						{:catch err}
							<div
								class="bg-dialog-bg-2 z-10 flex h-full w-full flex-col items-center justify-center gap-2"
							>
								<p class="text-lg font-bold">Preview not available</p>
								<p class="text-sm">{err}</p>
							</div>
						{/await}
					{:else if showFilePreview?.toLowerCase()?.endsWith('.csv')}
						{#await loadPreview() then previewContent}
							<div class="bg-dialog-bg-2 z-10 h-full w-full overflow-auto">
								{#if previewContent instanceof Array}
									{@const longestRow = Math.max(...previewContent[0].map((row) => row.length))}
									<div
										style={`grid-template-rows: repeat(${previewContent[0].length}, auto); grid-template-columns: repeat(${longestRow}, auto);`}
										class="grid"
									>
										{#each Array(previewContent[0].length).fill('') as _, rowIndex}
											{#each Array(longestRow).fill('') as _, columnIndex}
												{@const item = previewContent[0][rowIndex]?.[columnIndex]}
												<div
													class={`whitespace-pre-wrap border p-2 text-xs ${
														rowIndex == previewContent[0].length - 1 ? 'border-b' : 'border-b-0'
													} ${columnIndex == longestRow - 1 ? 'border-r' : 'border-r-0'}`}
												>
													{item ?? ''}
												</div>
											{/each}
										{/each}
									</div>
								{:else}
									<p class="h-full w-full overflow-auto whitespace-pre-wrap p-2 text-sm text-black">
										{previewContent}
									</p>
								{/if}
							</div>
						{:catch err}
							<div
								class="bg-dialog-bg-2 z-10 flex h-full w-full flex-col items-center justify-center gap-2"
							>
								<p class="text-lg font-bold">Preview not available</p>
								<p class="text-sm">{err}</p>
							</div>
						{/await}
					{:else if showFilePreview?.toLowerCase()?.endsWith('.md')}
						{#await loadPreview() then previewContent}
							{#if typeof previewContent == 'string'}
								<div class="bg-dialog-bg-2 z-10 h-full w-full">
									<p class="response-message h-full w-full overflow-auto whitespace-pre-wrap p-2">
										{@html converter.makeHtml(previewContent)}
									</p>
								</div>
							{/if}
						{:catch err}
							<div
								class="bg-dialog-bg-2 z-10 flex h-full w-full flex-col items-center justify-center gap-2"
							>
								<p class="text-lg font-bold">Preview not available</p>
								<p class="text-sm">{err}</p>
							</div>
						{/await}
					{:else}
						<div id="preview1" class="z-10 h-full w-full"></div>
					{/if}
				</div>
			{/if}
		{:else}
			<div class="flex h-full items-center justify-center">
				<LoadingSpinner class="h-6 w-6 text-secondary" />
			</div>
		{/if}
	</Dialog.Content>
</Dialog.Root>
