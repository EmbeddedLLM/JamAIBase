<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { tick } from 'svelte';
	import axios from 'axios';
	import toUpper from 'lodash/toUpper';
	import { v4 as uuidv4 } from 'uuid';
	import { page } from '$app/stores';
	import { genTableRows } from '$lib/components/tables/tablesStore';
	import logger from '$lib/logger';
	import type { GenTable, GenTableRow, GenTableStreamEvent } from '$lib/types';

	import { DeleteFileDialog, FileColumnView, FileSelect } from '$lib/components/tables/(sub)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import StarIcon from '$lib/icons/StarIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable;
	export let focusedCol: string | null;
	export let streamingRows: Record<string, string[]>;
	export let refetchTable: () => Promise<void>;

	let newRowForm: HTMLFormElement;
	let maxInputHeight = 36;
	let isAddingRow = false;
	let uploadColumns: Record<string, AbortController | string> = {};
	let isLoadingAddRow = false;
	let inputValues: Record<string, string> = {};
	let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null = null;

	$: tableData, isAddingRow, uploadColumns, resetMaxInputHeight();
	async function resetMaxInputHeight() {
		if (Object.entries(uploadColumns).some((val) => typeof val[1] === 'string')) {
			maxInputHeight = 150;
		} else if (tableData.cols.find((col) => col.dtype === 'file')) {
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
		genTableRows.addRow({
			ID: clientRowID,
			'Updated at': new Date().toISOString(),
			...(Object.fromEntries(
				Object.entries(data).map(([key, value]) => [key, { value: value?.toString() }])
			) as any)
		});

		streamingRows = {
			...streamingRows,
			[clientRowID]: tableData.cols
				.filter((col) => col.gen_config && !Object.keys(data).includes(col.id))
				.map((col) => col.id)
		};

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
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
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			genTableRows.deleteRow(clientRowID);
			delete streamingRows[clientRowID];
		} else {
			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			let rowId = '';
			let addedRow = false;
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error(toUpper(`${tableType}TBL_ROW_ADDSTREAMPARSE`), {
									parsing: sumValue,
									error: err
								});
								continue;
							}

							if (parsedValue.object === 'gen_table.completion.chunk') {
								if (parsedValue.choices[0].finish_reason) {
									switch (parsedValue.choices[0].finish_reason) {
										case 'error': {
											logger.error(toUpper(`${tableType}_ROW_ADDSTREAM`), parsedValue);
											console.error('STREAMING_ERROR', parsedValue);
											alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
											break;
										}
										default: {
											streamingRows = {
												...streamingRows,
												[parsedValue.row_id]: streamingRows[parsedValue.row_id].filter(
													(col) => col !== parsedValue.output_column_name
												)
											};
											break;
										}
									}
								} else {
									rowId = parsedValue.row_id;

									//* Add chunk to active row
									if (!addedRow) {
										genTableRows.updateRow(clientRowID, {
											ID: parsedValue.row_id,
											[parsedValue.output_column_name]: {
												value: parsedValue.choices[0].message.content ?? ''
											}
										} as GenTableRow);
										delete streamingRows[clientRowID];
										streamingRows = {
											...streamingRows,
											[parsedValue.row_id]: tableData.cols
												.filter((col) => col.gen_config && !Object.keys(data).includes(col.id))
												.map((col) => col.id)
										};
										addedRow = true;
									} else {
										genTableRows.stream(
											parsedValue.row_id,
											parsedValue.output_column_name,
											parsedValue.choices[0].message.content ?? ''
										);
									}
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					logger.error(toUpper(`${tableType}TBL_ROW_ADDSTREAM`), err);
					console.error(err);
					break;
				}
			}

			delete streamingRows[clientRowID];
			delete streamingRows[rowId];
			streamingRows = streamingRows;

			refetchTable();
		}
	}

	async function handleFilesUpload(files: File[], columnID: string) {
		const uploadController = new AbortController();
		uploadColumns[columnID] = uploadController;

		const formData = new FormData();
		formData.append('file', files[0]);

		try {
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/v1/files/upload/`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': $page.params.project_id
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
				const urlResponse = await fetch(`/api/v1/files/url/thumb`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						'x-project-id': $page.params.project_id
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
						description: CustomToastDesc,
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
	on:click={() => {
		if (!newRowForm.contains(document.activeElement)) {
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

<!-- svelte-ignore a11y-no-noninteractive-element-to-interactive-role -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<form
	role="row"
	tabindex="0"
	bind:this={newRowForm}
	on:click={() => (isAddingRow = true)}
	on:keydown={(event) => {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			event.currentTarget.requestSubmit();
		}
	}}
	on:submit|preventDefault={handleAddRow}
	style="grid-template-columns: 45px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
	'Updated at'
		? '320px'
		: '130px'} {tableData.cols.length - 2 !== 0
		? `repeat(${tableData.cols.length - 2}, minmax(320px, 1fr))`
		: ''};"
	class="sticky top-[36px] z-20 grid place-items-start h-min max-h-[100px] sm:max-h-[150px] text-xs sm:text-sm text-[#667085] bg-[#FAFBFC] data-dark:bg-[#1E2024] transition-[border-color,grid-template-columns] duration-200 group border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-[#E4E7EC] data-dark:border-[#333]"
>
	<div
		role="gridcell"
		class="sticky z-[1] left-0 flex flex-col items-center justify-center p-1 h-full w-full border-r border-[#E4E7EC] data-dark:border-[#333]"
	>
		<div
			class="absolute -z-10 top-0 -left-4 h-full w-[calc(100%_+_16px)] bg-[#FAFBFC] data-dark:bg-[#1E2024] {!isAddingRow
				? 'group-hover:bg-[#EDEEEF] data-dark:group-hover:bg-white/5'
				: ''}"
		/>
		<div class="absolute -z-10 top-0 -left-4 h-full w-[16px] bg-[#FAFBFC] data-dark:bg-[#1E2024]" />

		{#if isAddingRow}
			<Button
				variant="ghost"
				type="button"
				title="Cancel"
				on:click={(e) => {
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
				class="p-0 h-6 sm:h-7 rounded-full aspect-square"
			>
				<CloseIcon class="h-3.5 sm:h-4 text-black" />
			</Button>
		{:else}
			<AddIcon class="h-2.5" />
		{/if}
	</div>

	<div
		role="gridcell"
		class="col-span-2 flex items-center p-2 h-full w-full {isAddingRow
			? 'text-black border-r'
			: 'sticky left-[45.5px] text-[#667085] border-0 group-hover:bg-[#EDEEEF] data-dark:group-hover:bg-white/5'} break-words border-[#E4E7EC] data-dark:border-[#333]"
	>
		<div class="relative w-full">
			New Row

			{#if isAddingRow}
				<Button
					title="Add row"
					on:click={() => newRowForm.requestSubmit()}
					class="absolute top-1/2 -translate-y-1/2 right-0 p-0 h-6 aspect-square"
				>
					<StarIcon class="h-3.5 w-3.5" />
				</Button>
			{/if}
		</div>
	</div>

	{#each tableData.cols as column}
		{#if column.id !== 'ID' && column.id !== 'Updated at'}
			{@const columnFile = uploadColumns[column.id]}
			<!-- svelte-ignore a11y-interactive-supports-focus -->
			<div
				role="gridcell"
				class="flex justify-start {column.dtype === 'file' && typeof columnFile === 'string'
					? 'p-2'
					: 'p-0'} h-full max-h-[149px] w-full text-black break-words {isAddingRow
					? '[&:not(:last-child)]:border-r'
					: 'border-0 group-hover:bg-[#EDEEEF] data-dark:group-hover:bg-white/5'} border-[#E4E7EC] data-dark:border-[#333]"
			>
				{#if isAddingRow}
					{#if column.dtype === 'file'}
						{#if typeof columnFile !== 'string'}
							<FileSelect
								{tableType}
								controller={columnFile}
								selectCb={(files) => handleFilesUpload(files, column.id)}
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
							on:input={resizeTextarea}
							on:focus={resizeTextarea}
							class="max-h-[100px] sm:max-h-[150px] h-[36px] w-full p-2 placeholder:italic bg-transparent focus-visible:outline-1 focus-visible:outline focus-visible:outline-secondary resize-none"
						/>
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
