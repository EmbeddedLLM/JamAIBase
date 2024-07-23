<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { v4 as uuidv4 } from 'uuid';
	import { page } from '$app/stores';
	import { genTableRows } from '../tablesStore';
	import type { GenTable, GenTableRow, GenTableStreamEvent } from '$lib/types';

	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import logger from '$lib/logger';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable;
	export let focusedCol: string | null;
	export let streamingRows: Record<string, boolean>;
	export let refetchTable: () => void;

	let newRowForm: HTMLFormElement;
	let maxInputHeight = 36;
	let isAddingRow = false;
	let isLoadingAddRow = false;

	function resizeTextarea(e: Event & { currentTarget: EventTarget & HTMLTextAreaElement }) {
		for (const el of e.currentTarget.parentElement?.parentElement?.getElementsByTagName(
			'textarea'
		) ?? []) {
			if (el.scrollHeight > maxInputHeight) {
				maxInputHeight = el.scrollHeight >= 150 ? 150 : el.scrollHeight;
			}
		}

		e.currentTarget.style.height = `${maxInputHeight}px`;
		e.currentTarget.style.height =
			(e.currentTarget.scrollHeight >= 150 ? 150 : e.currentTarget.scrollHeight) + 'px';
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

		// Check if all required fields are filled
		if (
			Object.keys(obj).some(
				(key) => !tableData.cols.find((col) => col.id == key)?.gen_config && !obj[key]
			)
		) {
			return toast.error('Please fill in all required fields');
		}

		const data = Object.fromEntries(
			Object.entries(obj).filter(([key, value]) => value !== '' && value !== null)
		);

		isLoadingAddRow = true;
		isAddingRow = false;

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
			[clientRowID]: true
		};

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json'
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
				description: responseBody.message || JSON.stringify(responseBody)
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
								if (
									parsedValue.choices[0].finish_reason &&
									parsedValue.choices[0].finish_reason === 'error'
								) {
									logger.error(toUpper(`${tableType}_ROW_ADDSTREAM`), parsedValue);
									console.error('STREAMING_ERROR', parsedValue);
									alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
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
											[parsedValue.row_id]: true
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

			if (Object.keys(obj).every((key) => !obj[key])) {
				isAddingRow = false;
				maxInputHeight = 36;
			}
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
	style="grid-template-columns: 60px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
	'Updated at'
		? '320px'
		: '130px'} {tableData.cols.length - 2 !== 0
		? `repeat(${tableData.cols.length - 2}, minmax(320px, 1fr))`
		: ''};"
	class="sticky top-[40px] z-20 grid place-items-start h-min max-h-[150px] text-sm text-[#667085] bg-[#FAFBFC] data-dark:bg-[#1E2024] transition-[border-color,grid-template-columns] duration-200 group border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-[#E4E7EC] data-dark:border-[#333]"
>
	<div
		role="gridcell"
		class="sticky left-0 flex flex-col items-center justify-center p-1 h-full w-full border-r border-[#E4E7EC] data-dark:border-[#333]"
	>
		<div
			class="absolute -z-10 top-0 -left-4 h-full w-[calc(100%_+_16px)] bg-[#FAFBFC] data-dark:bg-[#1E2024] {!isAddingRow
				? 'group-hover:bg-[#EDEEEF] data-dark:group-hover:bg-white/5'
				: ''}"
		/>
		<div class="absolute -z-10 top-0 -left-4 h-full w-[16px] bg-[#FAFBFC] data-dark:bg-[#1E2024]" />

		{#if isAddingRow}
			<!-- <Button
				variant="ghost"
				type="submit"
				title="Add row"
				loading={isLoadingAddRow}
				disabled={isLoadingAddRow}
				class="p-0 h-8 rounded-full aspect-square"
			>
				<CheckIcon class="h-4 text-black" />
			</Button> -->
			<Button
				variant="ghost"
				type="button"
				title="Cancel"
				on:click={(e) => {
					e.stopPropagation();
					isAddingRow = false;
					maxInputHeight = 36;
				}}
				class="p-0 h-7 rounded-full aspect-square"
			>
				<CloseIcon class="h-4 text-black" />
			</Button>
		{:else}
			<AddIcon class="h-2.5" />

			<span class="absolute left-[68px] w-max">New Row</span>
		{/if}
	</div>

	{#if isAddingRow}
		<div
			role="gridcell"
			class="col-span-2 flex flex-col items-start p-2 h-full w-full font-medium text-black break-words border-r border-[#E4E7EC] data-dark:border-[#333]"
		>
			New Row
		</div>

		{#each tableData.cols as column}
			{#if column.id !== 'ID' && column.id !== 'Updated at'}
				<!-- svelte-ignore a11y-interactive-supports-focus -->
				<div
					role="gridcell"
					class="flex justify-start p-0 h-full max-h-[149px] w-full text-black break-words [&:not(:last-child)]:border-r border-[#E4E7EC] data-dark:border-[#333]"
				>
					<textarea
						name="new-row-{column.id}"
						placeholder={column.gen_config ? 'Optional, generated' : 'Required'}
						on:input={resizeTextarea}
						on:focus={resizeTextarea}
						class="max-h-[150px] h-[36px] w-full p-2 placeholder:italic bg-transparent focus-visible:outline-1 focus-visible:outline focus-visible:outline-secondary resize-none"
					/>
				</div>
			{/if}
		{/each}
	{:else}
		<div
			role="gridcell"
			style="grid-column: span {tableData.cols.length};"
			class="relative -z-10 flex justify-start p-2 overflow-auto whitespace-pre-line h-full max-h-[149px] w-full break-words group-hover:bg-[#EDEEEF] data-dark:group-hover:bg-white/5"
		>
			<span class="invisible">New Row</span>
		</div>
	{/if}
</form>
