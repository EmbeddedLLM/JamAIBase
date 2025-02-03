<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import axios from 'axios';
	import debounce from 'lodash/debounce';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/stores';
	import { fileColumnFiletypes } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let controller: (string | AbortController) | (AbortController | undefined);
	export let selectCb: (files: File[]) => void = handleSaveEditFile;
	export let column: GenTableCol;
	/** Edit cell function for tables */
	export let saveEditCell:
		| ((cellToUpdate: { rowID: string; columnID: string }, editedValue: string) => Promise<void>)
		| undefined = undefined;
	export let cellToUpdate: { rowID: string; columnID: string } | undefined = undefined;

	let container: HTMLDivElement;
	let filesDragover = false;

	/** Validate before upload */
	function handleSelectFiles(files: File[]) {
		container
			?.querySelectorAll('input[type="file"]')
			?.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (files.length > 1) {
			alert('Cannot upload multiple files in one column');
			return;
		}

		if (
			files.some(
				(file) =>
					!fileColumnFiletypes
						.filter(({ type }) => column.dtype === type)
						.map(({ ext }) => ext)
						.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(
				`Files must be of type: ${fileColumnFiletypes
					.filter(({ type }) => column.dtype === type)
					.map(({ ext }) => ext)
					.join(', ')
					.replaceAll('.', '')}`
			);
			return;
		}

		selectCb(files);
	}

	/** Upload function for tables */
	async function handleSaveEditFile(files: File[]) {
		if (!saveEditCell) {
			throw 'Missing prop saveEditCell';
		}

		if (!cellToUpdate) {
			throw 'Missing prop cellToUpdate';
		}

		controller = new AbortController();

		const formData = new FormData();
		formData.append('file', files[0]);

		try {
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/v1/files/upload`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': $page.params.project_id
				},
				signal: controller.signal
			});

			if (uploadRes.status !== 200) {
				logger.error(toUpper(`${tableType}TBL_ROW_UPLOAD`), {
					file: files[0].name,
					response: uploadRes.data
				});
				alert(
					'Failed to upload file: ' +
						(uploadRes.data.message || JSON.stringify(uploadRes.data)) +
						`\nRequest ID: ${uploadRes.data.request_id}`
				);
				return;
			} else {
				saveEditCell(cellToUpdate, uploadRes.data.uri);
			}
		} catch (err) {
			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error('ACTIONTBL_ROW_UPLOAD', err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}

		controller = undefined;
	}

	const handleDragLeave = () => (filesDragover = false);
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
	bind:this={container}
	on:dragover|preventDefault={(e) => {
		if (e.dataTransfer?.items) {
			if ([...e.dataTransfer.items].some((item) => item.kind === 'file')) {
				filesDragover = true;
			}
		}
	}}
	on:dragleave={debounce(handleDragLeave, 50)}
	on:drop|preventDefault={(e) => {
		filesDragover = false;
		if (e.dataTransfer?.items) {
			handleSelectFiles(
				[...e.dataTransfer.items]
					.map((item) => {
						if (item.kind === 'file') {
							const itemFile = item.getAsFile();
							if (itemFile) {
								return itemFile;
							} else {
								return [];
							}
						} else {
							return [];
						}
					})
					.flat()
			);
		} else {
			handleSelectFiles([...(e.dataTransfer?.files ?? [])]);
		}
	}}
	class="flex flex-col gap-1 px-2 py-2 h-full w-full"
>
	<Button
		variant="action"
		on:click={(e) => {
			if (controller === undefined) {
				e.currentTarget.querySelector('input')?.click();
			}
		}}
		class="gap-1 pl-3 w-min h-8 text-[#475467] {controller !== undefined
			? 'pr-2 pointer-events-none'
			: 'pr-3'}"
	>
		{#if controller === undefined}
			<AddIcon class="mr-1 h-3" />
			{#if filesDragover}
				Drop file to upload
			{:else}
				Add or drop a file
			{/if}
		{:else}
			<LoadingSpinner class="ml-0 mr-1 h-3 w-3" />
			Uploading
			<Button
				on:click={(e) => {
					e.stopPropagation();
					const uploadController = controller;
					if (typeof uploadController !== 'string') {
						uploadController?.abort();
					}
				}}
				variant="ghost"
				class="p-0 h-6 rounded-full aspect-square pointer-events-auto"
			>
				<CloseIcon class="h-4 w-4" />
			</Button>
		{/if}

		<input
			type="file"
			accept={fileColumnFiletypes
				.filter(({ type }) => column.dtype === type)
				.map(({ ext }) => ext)
				.join(',')}
			on:change|preventDefault={(e) => handleSelectFiles([...(e.currentTarget.files ?? [])])}
			multiple={false}
			class="fixed max-h-[0] max-w-0 !p-0 !border-none overflow-hidden"
		/>
	</Button>

	<span class="text-[#98A2B3]">
		Supports: {fileColumnFiletypes
			.filter(({ type }) => column.dtype === type)
			.map(({ ext }) => ext)
			.join(', ')}
	</span>
</div>
