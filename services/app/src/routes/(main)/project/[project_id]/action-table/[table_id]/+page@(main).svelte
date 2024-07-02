<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import { showRightDock } from '$globalStore';
	import { genTableRows } from '../../tablesStore';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol, GenTableStreamEvent } from '$lib/types';

	import ActionTable from './ActionTable.svelte';
	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import PastActionTables from './PastActionTables.svelte';
	import { AddColumnDialog, AddRowDialog, DeleteDialogs } from '../../(dialogs)';
	import AddTableDialog from './(dialogs)/AddTableDialog.svelte';
	import ColumnSettings from './ColumnSettings.svelte';
	import { toast } from 'svelte-sonner';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { Button } from '$lib/components/ui/button';
	import DblArrowRightIcon from '$lib/icons/DblArrowRightIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import CodeIcon from '$lib/icons/CodeIcon.svelte';
	import ArrowFilledRightIcon from '$lib/icons/ArrowFilledRightIcon.svelte';
	import ColumnIcon from '$lib/icons/ColumnIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';

	export let data;
	$: ({ table, userData } = data);
	let tableData: GenTable | undefined;
	$: if (table?.tableData || table?.rows) resetTable();
	const resetTable = () => {
		tableData = structuredClone(table?.tableData); // Client reorder column
		$genTableRows = structuredClone(table?.rows); // Client reorder rows
	};
	let streamingRows: Record<string, boolean> = {};

	let rightDockButton: HTMLButtonElement;
	let showRightDockButton = false;

	let selectedRows: string[] = [];

	let isAddingTable = false;
	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isAddingRow = false;
	let isDeletingTable: string | null = null;
	let isDeletingColumn: string | null = null;
	let isDeletingRow: string[] | null = null;
	let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean } = {
		column: null,
		showMenu: false
	};

	$: resetOnUpdate(data.table?.tableData);
	function resetOnUpdate(tableData: GenTable | undefined) {
		selectedRows = [];
		isColumnSettingsOpen = { column: null, showMenu: false };
	}

	function refetchTable() {
		//? Don't refetch while streaming
		if (Object.keys(streamingRows).length === 0) {
			invalidate('action-table:slug');
		}
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

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/rows/regen`, {
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
			logger.error('ACTIONTBL_ROW_REGEN', responseBody);
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
								logger.error('ACTIONTBL_ROW_REGENSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							if (parsedValue.object === 'gen_table.completion.chunk') {
								if (
									parsedValue.choices[0].finish_reason &&
									parsedValue.choices[0].finish_reason === 'error'
								) {
									logger.error('ACTIONTBL_ROW_REGENSTREAM', parsedValue);
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
					// logger.error('ACTIONTBL_ROW_REGENSTREAM', err);
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

	function mouseMoveListener(e: MouseEvent) {
		const tableArea = document.getElementById('action-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton.contains(el) ||
			(tableArea?.contains(el) && tableArea?.offsetWidth - (e.clientX - tableArea?.offsetLeft) < 75)
		) {
			showRightDockButton = true;
		} else {
			showRightDockButton = false;
		}
	}
</script>

<svelte:window on:mousemove={mouseMoveListener} />

<svelte:head>
	<title>{$page.params.table_id} - Action Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto) ${$showRightDock ? '20rem' : '0rem'};`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="action-table"
		class="relative flex flex-col pt-0 pb-12 min-h-0 max-h-screen min-w-0 overflow-hidden"
	>
		<BreadcrumbsBar />

		<div
			inert={isColumnSettingsOpen.showMenu}
			class="flex items-center justify-between px-4 py-3 gap-2"
		>
			<div class="flex items-center gap-2">
				<a href="/project/{$page.params.project_id}/action-table" class="[all:unset]">
					<Button variant="ghost" class="mr-2 p-0 h-8 rounded-full aspect-square">
						<ArrowLeft size={20} />
					</Button>
				</a>
				<ActionTableIcon class="flex-[0_0_auto] h-6 w-6 text-secondary" />
				<span class="font-medium line-clamp-1">
					{tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
				</span>
			</div>

			<div class="flex items-center gap-1.5">
				{#if tableData && $genTableRows}
					<div class="flex items-center gap-4">
						<Button
							on:click={() => (isAddingRow = true)}
							class="px-2.5 py-0 h-9 text-text bg-black/[0.04] data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1]"
						>
							<AddIcon class="w-3 h-3 mr-2" />
							Add row
						</Button>
					</div>

					<!-- <Button
						on:click={() => alert('open get code')}
						variant="ghost"
						class="flex gap-2 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
					>
						<CodeIcon class="h-5 w-5" />
						Get Code
					</Button> -->

					<DropdownMenu.Root>
						<DropdownMenu.Trigger asChild let:builder>
							<Button
								builders={[builder]}
								variant="ghost"
								class="flex gap-3 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
							>
								Actions
								<ArrowFilledRightIcon class="h-2.5 w-2.5" />
							</Button>
						</DropdownMenu.Trigger>
						<DropdownMenu.Content alignOffset={-40} transitionConfig={{ x: 5, y: -5 }}>
							<DropdownMenu.Group>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
										column
									</span>
								</DropdownMenu.Item>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#A67835] data-dark:text-[#DA9F47]">output</span>
										column
									</span>
								</DropdownMenu.Item>
							</DropdownMenu.Group>
							<!-- <DropdownMenu.Separator />
							<DropdownMenu.Group>
								<DropdownMenu.Item>
									<ImportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
									Import rows
								</DropdownMenu.Item>
								<DropdownMenu.Item>
									<ExportIcon class="h-3.5 w-3.5 mr-2 mb-[2px]" />
									Export rows
								</DropdownMenu.Item>
							</DropdownMenu.Group> -->
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
										<Trash2 class="h-3.5 w-3.5 mr-2 mb-[2px]" />
										Delete row(s)
									</DropdownMenu.Item>
								</DropdownMenu.Group>
							{/if}
						</DropdownMenu.Content>
					</DropdownMenu.Root>
				{/if}
			</div>
		</div>

		<ActionTable
			bind:userData
			bind:tableData
			bind:selectedRows
			bind:isColumnSettingsOpen
			bind:isDeletingColumn
			{streamingRows}
			{table}
		/>

		<ColumnSettings bind:isColumnSettingsOpen bind:isDeletingColumn />
	</section>

	<section
		class="relative z-[1] flex flex-col gap-2 min-h-0 bg-white data-dark:bg-[#303338] border-l border-[#DDD] data-dark:border-[#2A2A2A]"
	>
		<!-- Close right dock button -->
		<div
			class="absolute top-1/2 -translate-y-1/2 -left-16 flex items-center justify-end h-[80%] w-16 overflow-hidden pointer-events-none"
		>
			<button
				bind:this={rightDockButton}
				title="Show/hide action table history"
				on:click={() => ($showRightDock = !$showRightDock)}
				on:focusin={() => (showRightDockButton = true)}
				on:focusout={() => (showRightDockButton = false)}
				class={`p-1 bg-white data-dark:bg-[#303338] border border-[#DDD] data-dark:border-[#2A2A2A] rounded-l-xl ${
					showRightDockButton ? 'translate-x-0' : 'translate-x-11'
				} transition-transform duration-300 pointer-events-auto`}
			>
				<DblArrowRightIcon class={`w-8 h-8 ${!$showRightDock && 'rotate-180'}`} />
			</button>
		</div>

		<Button
			disabled={!$showRightDock}
			variant="outline"
			title="New table"
			on:click={() => (isAddingTable = true)}
			class="flex items-center gap-3 m-4 mx-6 mt-10 p-4 text-secondary hover:text-secondary text-center border-2 border-secondary bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-lg whitespace-nowrap overflow-hidden"
		>
			<AddIcon class="w-3 h-3" />
			New table
		</Button>

		<PastActionTables bind:isDeletingTable />
	</section>
</div>

<AddTableDialog bind:isAddingTable />
<AddColumnDialog bind:isAddingColumn tableType="action" />
<AddRowDialog bind:isAddingRow bind:streamingRows {refetchTable} tableType="action" />
<DeleteDialogs bind:isDeletingTable bind:isDeletingColumn bind:isDeletingRow tableType="action" />
