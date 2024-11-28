<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import toUpper from 'lodash/toUpper';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import { genTableRows } from '../tablesStore';
	import logger from '$lib/logger';
	import { chatTableStaticCols, knowledgeTableStaticCols } from '$lib/constants';
	import type { GenTable, GenTableCol, GenTableStreamEvent } from '$lib/types';

	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import StarIcon from '$lib/icons/StarIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let column: GenTableCol;
	export let tableData: GenTable | undefined;
	export let selectedRows: string[];
	export let streamingRows: Record<string, string[]>;
	export let isColumnSettingsOpen: { column: any; showMenu: boolean };
	export let isRenamingColumn: string | null;
	export let isDeletingColumn: string | null;
	export let refetchTable: () => Promise<void>;
	export let readonly;

	$: colType = !column.gen_config ? 'input' : 'output';

	async function handleRegen(regenStrategy: 'run_before' | 'run_selected' | 'run_after') {
		if (!tableData || !$genTableRows) return;
		if (Object.keys(streamingRows).length !== 0) return;

		const toRegenRowIds = selectedRows.filter((i) => !streamingRows[i]);
		if (toRegenRowIds.length === 0)
			return toast.info('Select a row to start generating', { id: 'row-select-req' });
		selectedRows = [];

		let colsToClear: string[];
		switch (regenStrategy) {
			case 'run_before': {
				colsToClear = tableData.cols
					.slice(0, tableData.cols.findIndex((col) => col.id === column.id) + 1)
					.map((col) => col.id);
				break;
			}
			case 'run_selected': {
				colsToClear = [column.id];
				break;
			}
			case 'run_after': {
				colsToClear = tableData.cols
					.slice(tableData.cols.findIndex((col) => col.id === column.id))
					.map((col) => col.id);
				break;
			}
		}

		streamingRows = {
			...streamingRows,
			...toRegenRowIds.reduce(
				(acc, curr) => ({
					...acc,
					[curr]: colsToClear
				}),
				{}
			)
		};

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: $genTableRows!.find((row) => row.ID === toRegenRowId)!
		}));
		genTableRows.clearOutputs(tableData, toRegenRowIds, colsToClear);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				regen_strategy: regenStrategy,
				output_column_id: column.id,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_REGENSTRAT`), responseBody);
			console.error(responseBody);
			toast.error('Failed to regenerate rows', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			genTableRows.revert(originalValues);
		} else {
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
			variant="ghost"
			on:click={(e) => e.stopPropagation()}
			title="Column actions"
			class="flex-[0_0_auto] !z-0 ml-auto p-0 h-7 w-7 aspect-square"
		>
			<MoreVertIcon class="h-[18px] w-[18px]" />
		</Button>
	</DropdownMenu.Trigger>
	<DropdownMenu.Content
		data-testid="column-actions-dropdown"
		alignOffset={-65}
		transitionConfig={{ x: 5, y: -5 }}
	>
		{#if colType === 'output'}
			<DropdownMenu.Group>
				<DropdownMenu.Item on:click={() => (isColumnSettingsOpen = { column, showMenu: true })}>
					<TuneIcon class="h-4 w-4 mr-2 mb-[1px] -translate-x-px" />
					<span class="-translate-x-0.5">Open settings</span>
				</DropdownMenu.Item>
			</DropdownMenu.Group>
		{/if}

		{#if colType === 'output' && !readonly && (tableType !== 'chat' || !chatTableStaticCols.includes(column.id)) && (tableType !== 'knowledge' || !knowledgeTableStaticCols.includes(column.id))}
			<DropdownMenu.Separator class="bg-[#E4E7EC]" />
		{/if}

		{#if !readonly && (tableType !== 'chat' || !chatTableStaticCols.includes(column.id)) && (tableType !== 'knowledge' || !knowledgeTableStaticCols.includes(column.id))}
			<DropdownMenu.Group>
				{#if selectedRows.length > 0}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger>
							<StarIcon class="h-[15px] w-[15px] mr-1.5" />
							<span>Regenerate</span>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent class="min-w-max">
							<DropdownMenu.Item on:click={() => handleRegen('run_selected')}>
								<span>This column</span>
							</DropdownMenu.Item>
							<DropdownMenu.Item on:click={() => handleRegen('run_before')}>
								<span>Up to this column</span>
							</DropdownMenu.Item>
							<DropdownMenu.Item on:click={() => handleRegen('run_after')}>
								<span>This column onwards</span>
							</DropdownMenu.Item>
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				<DropdownMenu.Item
					on:click={async () => {
						isRenamingColumn = column.id;
						//? Tick doesn't work
						setTimeout(() => document.getElementById('column-id-edit')?.focus(), 100);
					}}
				>
					<EditIcon class="h-3.5 w-3.5 mr-2" />
					<span>Rename</span>
				</DropdownMenu.Item>
				<DropdownMenu.Item on:click={() => (isDeletingColumn = column.id)} class="!text-[#F04438]">
					<Trash2 class="h-3.5 w-3.5 mr-2" />
					<span>Delete column</span>
				</DropdownMenu.Item>
			</DropdownMenu.Group>
		{/if}
	</DropdownMenu.Content>
</DropdownMenu.Root>
