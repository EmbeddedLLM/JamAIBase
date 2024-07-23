<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import xorWith from 'lodash/xorWith';
	import { v4 as uuidv4 } from 'uuid';
	import axios from 'axios';
	import Papa from 'papaparse';
	import Fuse from 'fuse.js';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { showLoadingOverlay } from '$globalStore';
	import { extendArray, textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableStreamEvent } from '$lib/types';

	import { ColumnMatchDialog } from '../(dialogs)';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ArrowFilledRightIcon from '$lib/icons/ArrowFilledRightIcon.svelte';
	import ColumnIcon from '$lib/icons/ColumnIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';
	import { genTableRows } from '../tablesStore';
	import { page } from '$app/stores';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable | undefined;
	export let selectedRows: string[];
	export let streamingRows: Record<string, boolean>;
	export let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean };
	export let isDeletingRow: string[] | null;
	export let refetchTable: () => void;

	let isMatchingImportCols: {
		filename: string;
		rows: Record<string, string>[];
		cols: { id: string; name: string }[];
	} | null = null;

	function handleImportTable() {
		if (!tableData) return;

		const fileInput = document.createElement('input');
		fileInput.type = 'file';
		fileInput.accept = '.csv';
		fileInput.onchange = (e) => {
			const file = (e.target as HTMLInputElement).files?.[0];
			if (!file) return;
			//@ts-ignore
			Papa.parse(file, {
				header: true,
				complete: (results) => {
					const filterFields = results.meta.fields?.filter(
						(field) => field !== 'ID' && field !== 'Updated at'
					);
					const filterTableCols = tableData?.cols
						.map((col) => col.id)
						.filter((field) => field !== 'ID' && field !== 'Updated at');

					const difference = xorWith(filterFields, filterTableCols);
					if (difference.length !== 0) {
						const sourceCols = extendArray(filterFields ?? [], filterTableCols?.length ?? 0).map(
							(col) => ({ id: uuidv4(), name: col })
						);
						const fuseSource = structuredClone(filterTableCols ?? []);
						const fuse = new Fuse(fuseSource, {
							threshold: 10,
							includeScore: true,
							shouldSort: true
						});

						let matchedSourceCols: {
							id: string;
							name: string;
							score: number;
						}[] = [];
						sourceCols.forEach((col) => {
							const res = fuse.search(col.name);
							if (res[0]?.refIndex !== undefined && !matchedSourceCols[res[0].refIndex]) {
								matchedSourceCols[res[0].refIndex] = { ...col, score: res[0]?.score ?? 0 };
							} else if (
								res[0]?.refIndex !== undefined &&
								matchedSourceCols[res[0].refIndex].score > (res[0].score ?? 1)
							) {
								let firstEmpty = matchedSourceCols.findIndex((v) => !v);
								firstEmpty = firstEmpty !== -1 ? firstEmpty : matchedSourceCols.length;
								matchedSourceCols[firstEmpty] = { ...col, score: res[0]?.score ?? 0 };
								[matchedSourceCols[firstEmpty], matchedSourceCols[res[0].refIndex]] = [
									matchedSourceCols[res[0].refIndex],
									matchedSourceCols[firstEmpty]
								];
							} else {
								let firstEmpty = matchedSourceCols.findIndex((v) => !v);
								firstEmpty = firstEmpty !== -1 ? firstEmpty : matchedSourceCols.length;
								matchedSourceCols[firstEmpty] = { ...col, score: 1 };
							}
						});
						matchedSourceCols = extendArray(
							Array.from(matchedSourceCols, (item) => item || { id: uuidv4(), name: '', score: 1 }),
							filterTableCols?.length ?? 0,
							{ id: uuidv4(), name: '', score: 1 }
						);

						isMatchingImportCols = {
							filename: file.name,
							rows: results.data as any[],
							cols: matchedSourceCols.map(({ id, name }) => ({ id, name }))
						};
					} else {
						uploadImportFile(file);
					}
				}
			});
		};
		fileInput.click();
	}

	async function uploadImportFile(file: File) {
		if (!tableData) return;

		const formData = new FormData();
		formData.append('file', file);
		formData.append('file_name', file.name);
		formData.append('table_id', tableData.id);

		$showLoadingOverlay = true;

		try {
			const response = await axios.post(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/import_data`,
				formData,
				{
					headers: {
						'Content-Type': 'multipart/form-data'
					}
				}
			);
			if (response.status != 200) {
				logger.error(toUpper(`${tableType}TBL_TBL_IMPORT`), response.data);
				alert('Failed to import data: ' + (response.data.message || JSON.stringify(response.data)));
			} else {
				refetchTable();

				if (response.data.err_message) {
					alert(
						'Error while uploading file: ' + response.data.message || JSON.stringify(response.data)
					);
				}
			}
		} catch (err) {
			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error(toUpper(`${tableType}TBL_TBL_IMPORTUPLOAD`), err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data))
				);
			}
		}

		$showLoadingOverlay = false;
	}

	async function handleExportTable() {
		if (!tableData || $showLoadingOverlay) return;

		$showLoadingOverlay = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableData.id}/export_data`
		);

		if (response.ok) {
			const responseBody = await response.text();
			textToFileDownload(`${tableData.id}`, responseBody);
		} else {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_TBL_EXPORTCSV`), responseBody);
			console.error(responseBody);
			toast.error('Failed to export table', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
		}

		$showLoadingOverlay = false;
	}

	async function handleRegenRow(toRegenRowIds: string[]) {
		if (!tableData || !$genTableRows) return;

		streamingRows = {
			...streamingRows,
			...toRegenRowIds.reduce((acc, curr) => ({ ...acc, [curr]: true }), {})
		};

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: $genTableRows!.find((row) => row.ID === toRegenRowId)!
		}));
		genTableRows.clearOutputs(tableData, toRegenRowIds);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_REGEN`), responseBody);
			console.error(responseBody);
			toast.error('Failed to regenerate rows', {
				description: responseBody.message || JSON.stringify(responseBody)
			});

			//? Revert back to original value
			genTableRows.revert(originalValues);
		} else {
			//Delete all data except for inputs
			genTableRows.clearOutputs(tableData, toRegenRowIds);

			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
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
								logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAMPARSE`), {
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
									logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAM`), parsedValue);
									console.error('STREAMING_ERROR', parsedValue);
									alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
								} else {
									//* Add chunk to active row'
									genTableRows.stream(
										parsedValue.row_id,
										parsedValue.output_column_name,
										parsedValue.choices[0].message.content ?? ''
									);
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					// logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAM`), err);
					console.error(err);

					//? Below necessary for retry
					for (const toRegenRowId of toRegenRowIds) {
						delete streamingRows[toRegenRowId];
					}
					streamingRows = streamingRows;

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		for (const toRegenRowId of toRegenRowIds) {
			delete streamingRows[toRegenRowId];
		}
		streamingRows = streamingRows;

		refetchTable();
	}
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger asChild let:builder>
		<Button
			builders={[builder]}
			variant="action"
			class="flex gap-3 p-0 px-3.5 h-9 border border-[#E5E5E5] data-dark:border-[#666] bg-white"
		>
			Actions
			<ArrowFilledRightIcon class="h-2.5 w-2.5" />
		</Button>
	</DropdownMenu.Trigger>
	<DropdownMenu.Content alignOffset={-40} transitionConfig={{ x: 5, y: -5 }}>
		<DropdownMenu.Group>
			<DropdownMenu.Item on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}>
				<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
				<span>
					Add
					<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
					column
				</span>
			</DropdownMenu.Item>
			<DropdownMenu.Item on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}>
				<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
				<span>
					Add
					<span class="text-[#A67835] data-dark:text-[#DA9F47]">output</span>
					column
				</span>
			</DropdownMenu.Item>
		</DropdownMenu.Group>
		<DropdownMenu.Separator />
		<DropdownMenu.Group>
			<DropdownMenu.Item on:click={handleImportTable}>
				<ImportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
				Import rows
			</DropdownMenu.Item>
			<DropdownMenu.Item on:click={handleExportTable}>
				<ExportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
				Export rows (.csv)
			</DropdownMenu.Item>
		</DropdownMenu.Group>
		{#if selectedRows.length}
			<DropdownMenu.Separator />
			<DropdownMenu.Group>
				{#if selectedRows.length}
					<DropdownMenu.Item
						on:click={() => {
							handleRegenRow(selectedRows.filter((i) => !streamingRows[i]));
							selectedRows = [];
						}}
						class="pl-[5px]"
					>
						<RegenerateIcon class="h-5 w-5 mr-[5px]" />
						Regenerate row
					</DropdownMenu.Item>
				{/if}
				<DropdownMenu.Item on:click={() => (isDeletingRow = selectedRows)}>
					<Trash_2 class="h-3.5 w-3.5 mr-2 mb-[2px]" />
					Delete row(s)
				</DropdownMenu.Item>
			</DropdownMenu.Group>
		{/if}
	</DropdownMenu.Content>
</DropdownMenu.Root>

<ColumnMatchDialog bind:isMatchingImportCols {tableData} {uploadImportFile} />
