<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import axios from 'axios';
	import debounce from 'lodash/debounce';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/state';
	import { fileColumnFiletypes } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		controller: (string | AbortController) | (AbortController | undefined);
		selectCb?: (files: File[]) => void;
		column: GenTableCol;
		/** Edit cell function for tables */
		saveEditCell?:
			| ((cellToUpdate: { rowID: string; columnID: string }, editedValue: string) => Promise<void>)
			| undefined;
		cellToUpdate?: { rowID: string; columnID: string } | undefined;
	}

	let {
		tableType,
		controller = $bindable(),
		selectCb = handleSaveEditFile,
		column,
		saveEditCell = undefined,
		cellToUpdate = undefined
	}: Props = $props();

	let container: HTMLDivElement | undefined = $state();
	let filesDragover = $state(false);

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
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/owl/files/upload`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': page.params.project_id
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

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={container}
	ondragover={(e) => {
		e.preventDefault();
		if (e.dataTransfer?.items) {
			if ([...e.dataTransfer.items].some((item) => item.kind === 'file')) {
				filesDragover = true;
			}
		}
	}}
	ondragleave={debounce(handleDragLeave, 50)}
	ondrop={(e) => {
		e.preventDefault();
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
	class="flex h-full w-full flex-col gap-1 px-2 py-2"
>
	<Button
		variant="action"
		onclick={(e) => {
			if (controller === undefined) {
				e.currentTarget.querySelector('input')?.click();
			}
		}}
		class="h-8 w-min gap-1 pl-3 text-[#475467] {controller !== undefined
			? 'pointer-events-none pr-2'
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
				onclick={(e) => {
					e.stopPropagation();
					const uploadController = controller;
					if (typeof uploadController !== 'string') {
						uploadController?.abort();
					}
				}}
				variant="ghost"
				class="pointer-events-auto aspect-square h-6 rounded-full p-0"
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
			onchange={(e) => {
				e.preventDefault();
				handleSelectFiles([...(e.currentTarget.files ?? [])]);
			}}
			multiple={false}
			class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
		/>
	</Button>

	<span class="text-[#98A2B3]">
		Supports: {fileColumnFiletypes
			.filter(({ type }) => column.dtype === type)
			.map(({ ext }) => ext)
			.join(', ')}
	</span>
</div>
