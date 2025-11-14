<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/state';
	import toUpper from 'lodash/toUpper';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import logger from '$lib/logger';
	import { tableStaticCols } from '$lib/constants';
	import type { GenTable, GenTableCol, GenTableStreamEvent } from '$lib/types';

	import Portal from '$lib/components/Portal.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import StarIcon from '$lib/icons/StarIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
		column: GenTableCol;
		refetchTable: () => Promise<void>;
		readonly: any;
	}

	let { tableType, tableData, column, refetchTable, readonly }: Props = $props();

	let colType = $derived(!column.gen_config ? 'input' : 'output');

	async function handleRegen(regenStrategy: 'run_before' | 'run_selected' | 'run_after') {
		if (!tableData || !tableRowsState.rows) return;
		if (Object.keys(tableState.streamingRows).length !== 0) return;

		const toRegenRowIds = tableState.selectedRows.filter((i) => !tableState.streamingRows[i]);
		if (toRegenRowIds.length === 0)
			return toast.info('Select a row to start generating', { id: 'row-select-req' });
		tableState.setSelectedRows([]);

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

		tableState.addStreamingRows(
			toRegenRowIds.reduce(
				(acc, curr) => ({
					...acc,
					[curr]: colsToClear
				}),
				{}
			)
		);

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: tableRowsState.rows!.find((row) => row.ID === toRegenRowId)!
		}));
		tableRowsState.clearOutputs(tableData, toRegenRowIds, colsToClear);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: page.params.table_id,
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
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			tableRowsState.revert(originalValues);
		} else {
			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			// let references: Record<string, Record<string, ChatReferences>> | null = null;
			let buffer = '';
			// eslint-disable-next-line no-constant-condition
			while (true) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					buffer += value;
					const lines = buffer.split('\n'); //? Split by \n to handle collation
					buffer = lines.pop() || '';

					let parsedEvent: { data: GenTableStreamEvent } | undefined = undefined;
					for (const line of lines) {
						if (line === '') {
							if (parsedEvent) {
								if (parsedEvent.data.object === 'gen_table.completion.chunk') {
									if (parsedEvent.data.choices[0].finish_reason) {
										switch (parsedEvent.data.choices[0].finish_reason) {
											case 'error': {
												logger.error(toUpper(`${tableType}_ROW_ADDSTREAM`), parsedEvent.data);
												console.error('STREAMING_ERROR', parsedEvent.data);
												alert(
													`Error while streaming: ${parsedEvent.data.choices[0].message.content}`
												);
												break;
											}
											default: {
												const streamingCols =
													tableState.streamingRows[parsedEvent.data.row_id]?.filter(
														(col) => col !== parsedEvent?.data.output_column_name
													) ?? [];
												if (streamingCols.length === 0) {
													tableState.delStreamingRows([parsedEvent.data.row_id]);
												} else {
													tableState.addStreamingRows({
														[parsedEvent.data.row_id]: streamingCols
													});
												}
												break;
											}
										}
									} else {
										//* Add chunk to active row'
										tableRowsState.stream(
											parsedEvent.data.row_id,
											parsedEvent.data.output_column_name,
											parsedEvent.data.choices[0].message.content ?? ''
										);
									}
								} else {
									console.log('Unknown message:', parsedEvent);
								}
							} else {
								console.warn('Unknown event object:', parsedEvent);
							}
						} else if (line.startsWith('data: ')) {
							if (line.slice(6) === '[DONE]') break;
							parsedEvent = { ...(parsedEvent ?? {}), data: JSON.parse(line.slice(6)) };
						} /*  else if (line.startsWith('event: ')) {
						parsedEvent = { ...(parsedEvent ?? {}), event: line.slice(7) };
					} */
					}
				} catch (err) {
					// logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAM`), err);
					console.error(err);

					//? Below necessary for retry
					tableState.delStreamingRows(toRegenRowIds);

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		tableState.delStreamingRows(toRegenRowIds);
		refetchTable();
	}

	let animationFrameId: ReturnType<typeof requestAnimationFrame> | null = $state(null);
	let tooltip: HTMLDivElement | undefined = $state();
	let tooltipPos = $state({ x: 0, y: 0, visible: false });
	function handleMouseOver(event: MouseEvent) {
		if (animationFrameId) {
			cancelAnimationFrame(animationFrameId);
		}

		animationFrameId = requestAnimationFrame(() => {
			if (!tooltip) return;
			let x = event.clientX;
			let y = event.clientY;

			if (window.innerWidth - event.clientX - 15 < tooltip.offsetWidth) {
				x -= tooltip.offsetWidth;
			} else {
				x += 10;
				y += 10;
			}

			if (window.innerHeight - event.clientY < tooltip.offsetHeight) {
				y -= tooltip.offsetHeight;
			}

			tooltipPos = { x, y, visible: true };

			animationFrameId = null;
		});
	}
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="ghost"
				onclick={(e) => e.stopPropagation()}
				title="Column actions"
				class="!z-0 ml-auto aspect-square h-7 w-7 flex-[0_0_auto] p-0"
			>
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>
	<DropdownMenu.Content data-testid="column-actions-dropdown" alignOffset={-65}>
		{#if colType === 'output'}
			<DropdownMenu.Group>
				<DropdownMenu.Item onclick={() => tableState.setColumnSettings({ column, isOpen: true })}>
					<TuneIcon class="mb-[1px] mr-2 h-4 w-4 -translate-x-px" />
					<span class="-translate-x-0.5">Open settings</span>
				</DropdownMenu.Item>
			</DropdownMenu.Group>
		{/if}

		{#if colType === 'output' && !readonly && !tableStaticCols[tableType].includes(column.id)}
			<DropdownMenu.Separator class="bg-[#E4E7EC]" />
		{/if}

		{#if !readonly && !tableStaticCols[tableType].includes(column.id)}
			<DropdownMenu.Group>
				{#if colType === 'output'}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							disabled={tableState.selectedRows.length === 0}
							class="relative data-[disabled]:opacity-50"
						>
							{#if tableState.selectedRows.length === 0}
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<!-- svelte-ignore a11y_mouse_events_have_key_events -->
								<div
									onmousemove={handleMouseOver}
									onmouseleave={() => {
										if (animationFrameId) cancelAnimationFrame(animationFrameId);
										tooltipPos.visible = false;
									}}
									class="pointer-events-auto absolute -bottom-1 -top-1 left-0 right-0 cursor-default"
								></div>
							{/if}

							<StarIcon class="mr-1.5 h-[15px] w-[15px]" />
							<span>Regenerate</span>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent class="min-w-max">
							<DropdownMenu.Item onclick={() => handleRegen('run_selected')}>
								<span>This column</span>
							</DropdownMenu.Item>
							<DropdownMenu.Item onclick={() => handleRegen('run_before')}>
								<span>Up to this column</span>
							</DropdownMenu.Item>
							<DropdownMenu.Item onclick={() => handleRegen('run_after')}>
								<span>This column onwards</span>
							</DropdownMenu.Item>
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}

				<DropdownMenu.Item
					onclick={async () => {
						tableState.setRenamingCol(column.id);
						//? Tick doesn't work
						setTimeout(() => document.getElementById('column-id-edit')?.focus(), 200);
					}}
				>
					<EditIcon class="mr-2 h-3.5 w-3.5" />
					<span>Rename</span>
				</DropdownMenu.Item>
				<DropdownMenu.Item
					onclick={() => tableState.setDeletingCol(column.id)}
					class="!text-[#F04438]"
				>
					<Trash2 class="mr-2 h-3.5 w-3.5" />
					<span>Delete column</span>
				</DropdownMenu.Item>
			</DropdownMenu.Group>
		{/if}
	</DropdownMenu.Content>
</DropdownMenu.Root>

<Portal>
	<Tooltip
		bind:tooltip
		class="z-[9999]"
		style="--arrow-size: 10px; left: {tooltipPos.x}px; top: {tooltipPos.y}px; visibility: {tooltipPos.visible
			? 'visible'
			: 'hidden'}"
		showArrow={false}
	>
		Select at least one row to regenerate
	</Tooltip>
</Portal>
