<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { page } from '$app/stores';
	import { genTableRows } from '../tablesStore';
	import type { GenTable, GenTableStreamEvent } from '$lib/types';

	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import logger from '$lib/logger';

	export let isAddingRow: boolean;
	export let tableType: 'action' | 'knowledge' | 'chat';
	export let streamingRows: Record<string, boolean>;
	export let refetchTable: () => void;

	let isLoadingAddRow: boolean;

	$: tableData = $page.data.table?.tableData as GenTable; // For types

	let form: HTMLFormElement;

	async function handleAddRow(e: SubmitEvent) {
		if (isLoadingAddRow) return;
		const form = e.target as HTMLFormElement;
		const formData = new FormData(form);
		const obj = Object.fromEntries(
			Array.from(formData.keys()).map((key) => [
				key,
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

		isAddingRow = false;
		isLoadingAddRow = false;

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_ADD`), responseBody);
			toast.error('Failed to add row', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
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
									streamingRows = {
										...streamingRows,
										[parsedValue.row_id]: true
									};

									//* Add chunk to active row
									if (!addedRow) {
										genTableRows.addRow({
											...(Object.fromEntries(
												Object.entries(data).map(([key, value]) => [
													key,
													{ value: value as string }
												])
											) as any),
											ID: parsedValue.row_id,
											'Updated at': new Date().toISOString(),
											[parsedValue.output_column_name]: {
												value: parsedValue.choices[0].message.content ?? ''
											}
										});
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

			delete streamingRows[rowId];
			streamingRows = streamingRows;

			refetchTable();
		}
	}
</script>

<Dialog.Root bind:open={isAddingRow}>
	<Dialog.Content class="max-h-[90vh] min-w-[35rem]">
		<Dialog.Header>New row</Dialog.Header>

		<form
			bind:this={form}
			on:submit|preventDefault={handleAddRow}
			class="grow w-full overflow-auto"
		>
			<div class="grow py-3 h-full w-full overflow-auto">
				{#if !tableData.cols.filter((col) => col.id !== 'ID' && col.id !== 'Updated at').length}
					<div class="flex items-center justify-center w-full h-32">
						<p class="text-[#999] data-dark:text-[#C9C9C9]">No columns</p>
					</div>
				{:else}
					{#each tableData.cols.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') as column}
						<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
							<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								{column.id} ({column.dtype}){!column.gen_config ? '*' : ''}
							</span>

							<InputText
								id={column.id}
								name={column.id}
								placeholder={column.gen_config ? 'Optional, generated' : 'Required'}
							/>
						</div>
					{/each}
				{/if}
			</div>

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoadingAddRow}
				class="hidden relative grow px-6 rounded-full"
			>
				Add
			</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={() => form.requestSubmit()}
					type="button"
					loading={isLoadingAddRow}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
