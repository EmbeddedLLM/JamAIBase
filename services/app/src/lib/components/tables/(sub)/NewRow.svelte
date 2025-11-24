<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import axios from 'axios';
	import toUpper from 'lodash/toUpper';
	import { v4 as uuidv4 } from 'uuid';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableRow, GenTableStreamEvent } from '$lib/types';

	import { DeleteFileDialog, FileColumnView, FileSelect } from '$lib/components/tables/(sub)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import StarIcon from '$lib/icons/StarIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable;
		focusedCol: string | null;
		refetchTable: () => Promise<void>;
		class?: string | undefined | null;
	}

	let {
		tableType,
		tableData,
		focusedCol,
		refetchTable,
		class: className = undefined
	}: Props = $props();

	let newRowForm: HTMLFormElement | undefined = $state();
	let maxInputHeight = $state(36);
	let isAddingRow = $state(false);
	let uploadColumns: Record<string, AbortController | string> = $state({});
	let isLoadingAddRow = false;
	let inputValues: Record<string, string> = $state({});
	let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null = $state(null);

	$effect(() => {
		tableData;
		isAddingRow;
		uploadColumns;
		resetMaxInputHeight();
	});
	async function resetMaxInputHeight() {
		if (Object.entries(uploadColumns).some((val) => typeof val[1] === 'string')) {
			maxInputHeight = 150;
		} else if (
			tableData.cols.find(
				(col) => col.dtype === 'image' || col.dtype === 'audio' || col.dtype === 'document'
			)
		) {
			maxInputHeight = 72;
		} else {
			maxInputHeight = 32;
		}

		await tick();
		resizeTextarea();
	}

	function resizeTextarea() {
		if (!newRowForm) return;

		const textareas = newRowForm.getElementsByTagName('textarea') ?? [];
		for (const el of textareas) {
			if (el.scrollHeight > maxInputHeight) {
				maxInputHeight = el.scrollHeight >= 150 ? 150 : el.scrollHeight;
			}
		}

		for (const el of textareas) {
			el.style.height = `${maxInputHeight}px`;
			el.style.height = (el.scrollHeight >= 150 ? 150 : el.scrollHeight) + 'px';
		}
	}

	async function handleAddRow(e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }) {
		e.preventDefault();
		if (isLoadingAddRow) return;
		const formData = new FormData(e.currentTarget);
		const obj = Object.fromEntries(
			Array.from(formData.keys()).map((key) => [
				key.replace('new-row-', ''),
				formData.getAll(key).length > 1 ? formData.getAll(key) : formData.get(key)
			])
		);

		const data = Object.fromEntries(
			Object.entries(obj).filter(([key, value]) => value !== '' && value !== null)
		);

		isLoadingAddRow = true;
		isAddingRow = false;
		uploadColumns = {};
		inputValues = {};

		const clientRowID = uuidv4();
		tableRowsState.addRow({
			ID: clientRowID,
			'Updated at': new Date().toISOString(),
			...(Object.fromEntries(
				Object.entries(data).map(([key, value]) => [key, { value: value?.toString() }])
			) as any)
		});

		tableState.addStreamingRows({
			[clientRowID]: tableData.cols
				.filter((col) => col.gen_config && !Object.keys(data).includes(col.id))
				.map((col) => col.id)
		});

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				table_id: page.params.table_id,
				data: [data],
				stream: true
			})
		});

		isLoadingAddRow = false;

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_ADD`), responseBody);
			toast.error('Failed to add row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			tableRowsState.deleteRow(clientRowID);
			tableState.delStreamingRows([clientRowID]);
		} else {
			const { row_id } = await tableRowsState.parseStream(
				tableState,
				response.body!.pipeThrough(new TextDecoderStream()).getReader(),
				clientRowID
			);

			tableState.delStreamingRows([clientRowID, row_id]);
			refetchTable();
		}
	}

	async function handleFilesUpload(files: File[], columnID: string) {
		const uploadController = new AbortController();
		uploadColumns[columnID] = uploadController;

		const formData = new FormData();
		formData.append('file', files[0]);

		try {
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/owl/files/upload`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': page.params.project_id
				},
				signal: uploadController.signal
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
				const urlResponse = await fetch(`/api/owl/files/url/thumb`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						'x-project-id': page.params.project_id ?? ''
					},
					body: JSON.stringify({
						uris: [uploadRes.data.uri]
					})
				});
				const urlBody = await urlResponse.json();

				if (urlResponse.ok) {
					uploadColumns[columnID] = urlBody.urls[0];
				} else {
					uploadColumns[columnID] = uploadRes.data.uri;
					toast.error('Failed to retrieve thumbnail', {
						id: urlBody.message || JSON.stringify(urlBody),
						description: CustomToastDesc as any,
						componentProps: {
							description: urlBody.message || JSON.stringify(urlBody),
							requestID: urlBody.request_id
						}
					});
				}

				inputValues[columnID] = uploadRes.data.uri;
			}
		} catch (err) {
			delete uploadColumns[columnID];
			uploadColumns = uploadColumns;

			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error(toUpper(`${tableType}TBL_ROW_UPLOAD`), err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}
	}
</script>

<svelte:window
	onclick={() => {
		if (!newRowForm?.contains(document.activeElement)) {
			const formData = new FormData(newRowForm);
			const obj = Object.fromEntries(
				Array.from(formData.keys()).map((key) => [
					key.replace('new-row-', ''),
					formData.getAll(key).length > 1 ? formData.getAll(key) : formData.get(key)
				])
			);

			if (!Object.keys(obj).every((key) => !obj[key]) || Object.keys(uploadColumns).length !== 0) {
				return;
			}

			isAddingRow = false;
			maxInputHeight = 36;
			uploadColumns = {};
			inputValues = {};
		}
	}}
/>

<!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<form
	role="row"
	tabindex="0"
	bind:this={newRowForm}
	onclick={() => (isAddingRow = true)}
	onkeydown={(event) => {
		if (!isAddingRow && event.key === ' ') {
			isAddingRow = true;
		}

		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			if (isAddingRow) event.currentTarget.requestSubmit();
		}
	}}
	onsubmit={handleAddRow}
	style="grid-template-columns: 45px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
	'Updated at'
		? '320px'
		: '130px'} {tableState.templateCols};"
	class={cn(
		'group sticky top-[36px] z-20 grid h-min max-h-[100px] place-items-start border-b border-l border-[#E4E7EC] border-l-transparent border-r-transparent bg-[#F2F4F7] text-xs text-[#667085] data-dark:border-[#333] data-dark:border-l-transparent data-dark:border-r-transparent data-dark:bg-[#1E2024] sm:max-h-[150px] sm:text-sm',
		className
	)}
>
	<div
		role="gridcell"
		class="sticky left-0 z-[1] flex h-full w-full flex-col items-center justify-center border-r border-[#E4E7EC] p-1 data-dark:border-[#333]"
	>
		<div
			class="absolute -left-4 top-0 -z-10 h-full w-[calc(100%_+_16px)] bg-[#F2F4F7] data-dark:bg-[#1E2024] {!isAddingRow
				? 'group-hover:bg-[#E7EBF1] data-dark:group-hover:bg-white/5'
				: ''}"
		></div>
		<div
			class="absolute -left-4 top-0 -z-10 h-full w-[16px] bg-[#F2F4F7] data-dark:bg-[#1E2024]"
		></div>

		{#if isAddingRow}
			<Button
				variant="ghost"
				type="button"
				title="Cancel"
				onclick={(e) => {
					e.stopPropagation();

					const formData = new FormData(newRowForm);
					const obj = Object.fromEntries(
						Array.from(formData.keys()).map((key) => [
							key.replace('new-row-', ''),
							formData.getAll(key).length > 1 ? formData.getAll(key) : formData.get(key)
						])
					);

					if (
						(!Object.keys(obj).every((key) => !obj[key]) ||
							Object.keys(uploadColumns).length !== 0) &&
						!confirm('Discard unsaved changes?')
					) {
						return;
					}

					isAddingRow = false;
					maxInputHeight = 36;
					uploadColumns = {};
					inputValues = {};
				}}
				class="aspect-square h-6 rounded-full p-0 sm:h-7"
			>
				<CloseIcon class="h-3.5 text-black sm:h-4" />
			</Button>
		{:else}
			<AddIcon class="h-2.5" />
		{/if}
	</div>

	<div
		role="gridcell"
		class="col-span-2 flex h-full w-full items-center p-2 {isAddingRow
			? 'border-r text-black'
			: 'sticky left-[45.5px] border-0 text-[#667085] group-hover:bg-[#E7EBF1] data-dark:group-hover:bg-white/5'} break-words border-[#E4E7EC] data-dark:border-[#333]"
	>
		<div class="relative w-full">
			New Row

			{#if isAddingRow}
				<Button
					title="Add row"
					onclick={() => newRowForm?.requestSubmit()}
					class="absolute right-0 top-1/2 aspect-square h-6 -translate-y-1/2 p-0"
				>
					<StarIcon class="h-3.5 w-3.5" />
				</Button>
			{/if}
		</div>
	</div>

	{#each tableData.cols as column}
		{#if column.id !== 'ID' && column.id !== 'Updated at'}
			{@const columnFile = uploadColumns[column.id]}
			<!-- svelte-ignore a11y_interactive_supports_focus -->
			<div
				role="gridcell"
				class="flex justify-start {(column.dtype === 'image' ||
					column.dtype === 'audio' ||
					column.dtype === 'document') &&
				typeof columnFile === 'string'
					? 'p-2'
					: 'p-0'} h-full max-h-[149px] w-full break-words text-black {isAddingRow
					? '[&:not(:last-child)]:border-r'
					: 'border-0 group-hover:bg-[#E7EBF1] data-dark:group-hover:bg-white/5'} border-[#E4E7EC] data-dark:border-[#333]"
			>
				{#if isAddingRow}
					{#if column.dtype === 'image' || column.dtype === 'audio' || column.dtype === 'document'}
						{#if typeof columnFile !== 'string'}
							<FileSelect
								{tableType}
								controller={columnFile}
								selectCb={(files) => handleFilesUpload(files, column.id)}
								{column}
							/>
						{:else}
							<FileColumnView
								{tableType}
								columnID={column.id}
								fileUri={inputValues[column.id]}
								fileUrl={columnFile}
								bind:isDeletingFile
							/>
						{/if}
						<input
							tabindex={-1}
							bind:value={inputValues[column.id]}
							name="new-row-{column.id}"
							class="absolute h-0 w-0"
						/>
					{:else}
						<textarea
							name="new-row-{column.id}"
							placeholder={column.gen_config ? 'Optional, generated' : 'Required'}
							oninput={resizeTextarea}
							onfocus={resizeTextarea}
							class="h-[36px] max-h-[100px] w-full resize-none bg-transparent p-2 placeholder:italic focus-visible:outline focus-visible:outline-1 focus-visible:outline-secondary sm:max-h-[150px]"
						></textarea>
					{/if}
				{/if}
			</div>
		{/if}
	{/each}
</form>

<DeleteFileDialog
	bind:isDeletingFile
	deleteCb={() => {
		if (isDeletingFile) {
			delete uploadColumns[isDeletingFile.columnID];
			uploadColumns = uploadColumns;
			delete inputValues[isDeletingFile.columnID];
			inputValues = inputValues;
			isDeletingFile = null;
		}
	}}
/>
