<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { genTableRows, tableState } from '$lib/components/tables/tablesStore';
	import { cn, isValidUri } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableRow, UserRead } from '$lib/types';

	import {
		ColumnHeader,
		DeleteFileDialog,
		FileColumnView,
		FileSelect,
		FileThumbsFetch
	} from '$lib/components/tables/(sub)';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import NoRowsGraphic from './(svg)/NoRowsGraphic.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	export let userData: UserRead | undefined;
	export let tableData: GenTable | undefined;
	export let tableError: { error: number; message?: any } | undefined;
	export let readonly = false;
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;

	let rowThumbs: { [rowID: string]: { [colID: string]: { value: string; url: string } } } = {};
	let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null = null;
	let uploadController: AbortController | undefined = undefined;

	//? Expanding ID and Updated at columns
	let focusedCol: string | null = null;

	async function handleSaveEdit(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLTextAreaElement;
		}
	) {
		if (!tableData || !$genTableRows) return;
		if (!$tableState.editingCell) return;

		const editedValue = e.currentTarget.value;
		const cellToUpdate = $tableState.editingCell;

		await saveEditCell(cellToUpdate, editedValue);
	}

	async function saveEditCell(
		cellToUpdate: { rowID: string; columnID: string },
		editedValue: string
	) {
		if (!tableData || !$genTableRows) return;

		//? Optimistic update
		const originalValue = $genTableRows.find((row) => row.ID === cellToUpdate!.rowID)?.[
			cellToUpdate.columnID
		];
		genTableRows.setCell(cellToUpdate, editedValue);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/rows/update`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: tableData.id,
				row_id: cellToUpdate.rowID,
				data: {
					[cellToUpdate.columnID]: editedValue
				}
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_TBL_ROWEDIT', responseBody);
			toast.error('Failed to edit row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			genTableRows.setCell(cellToUpdate, originalValue);
		} else {
			tableState.setEditingCell(null);
			refetchTable();
		}
	}

	let shiftOrigin: number | null = null;
	//? Select row
	function handleSelectRow(
		e: CustomEvent<{ event: MouseEvent; value: boolean }>,
		row: GenTableRow
	) {
		if (!tableData || !$genTableRows) return;
		//? Select multiple rows with shift key
		const rowIndex = $genTableRows.findIndex(({ ID }) => ID === row.ID);
		if (e.detail.event.shiftKey && $tableState.selectedRows.length && shiftOrigin != null) {
			if (shiftOrigin < rowIndex) {
				tableState.setSelectedRows([
					...$tableState.selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
					...$genTableRows.slice(shiftOrigin, rowIndex + 1).map(({ ID }) => ID)
				]);
			} else if (shiftOrigin > rowIndex) {
				tableState.setSelectedRows([
					...$tableState.selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
					...$genTableRows.slice(rowIndex, shiftOrigin + 1).map(({ ID }) => ID)
				]);
			} else {
				tableState.toggleRowSelection(row.ID);
			}
		} else {
			tableState.toggleRowSelection(row.ID);
			shiftOrigin = rowIndex;
		}
	}

	function keyboardNavigate(e: KeyboardEvent) {
		if (!tableData || !$genTableRows) return;
		const isCtrl = window.navigator.userAgent.indexOf('Mac') != -1 ? e.metaKey : e.ctrlKey;
		const activeElement = document.activeElement as HTMLElement;
		const isInputActive = activeElement.tagName == 'INPUT' || activeElement.tagName == 'TEXTAREA';
		if (isCtrl && e.key === 'a' && !isInputActive) {
			e.preventDefault();

			if (Object.keys($tableState.streamingRows).length !== 0) return;

			tableState.setSelectedRows([
				...$tableState.selectedRows.filter((i) => !$genTableRows?.some(({ ID }) => ID === i)),
				...$genTableRows.map(({ ID }) => ID)
			]);
		}

		if (e.key === 'Escape') {
			tableState.setEditingCell(null);
		}
	}

	function handleUploadClick() {
		(document.querySelector('input[type="file"]') as HTMLElement).click();
	}

	onDestroy(() => {
		$genTableRows = undefined;
		tableState.reset();
	});
</script>

<svelte:document
	on:mousedown={(e) => {
		const editingCell = document.querySelector('[data-editing="true"]');
		//@ts-ignore
		if (e.target && editingCell && !editingCell.contains(e.target)) {
			tableState.setEditingCell(null);
		}
	}}
	on:keydown={keyboardNavigate}
/>

{#if tableData}
	<div
		data-testid="table-area"
		inert={$tableState.columnSettings.isOpen}
		class="grow flex flex-col w-full min-h-0"
	>
		<div
			on:scroll={(e) => {
				//? Used to prevent elements showing through the padding between side nav and table header
				//FIXME: Use transform for performance
				const el = document.getElementById('checkbox-bg-obscure');
				if (el) {
					el.style.left = `-${e.currentTarget.scrollLeft > 20 ? 20 : e.currentTarget.scrollLeft}px`;
				}
			}}
			role="grid"
			style={$genTableRows?.length !== 0
				? `grid-template-rows: 36px ${
						$genTableRows ? `repeat(${$genTableRows.length}, min-content)` : 'minmax(0, 1fr)'
					};`
				: undefined}
			class="grow relative grid px-2 overflow-auto"
		>
			<div
				role="row"
				style="grid-template-columns: 45px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
				'Updated at'
					? '320px'
					: '130px'} {$tableState.templateCols};"
				class={cn(
					'sticky top-0 z-20 grid h-[36px] text-xs sm:text-sm border border-[#E4E7EC] data-dark:border-[#333] rounded-lg bg-white data-dark:bg-[#42464E]',
					Object.keys($tableState.colSizes).length !== 0 && 'w-min',
					!$tableState.resizingCol && 'transition-[grid-template-columns] duration-200'
				)}
			>
				<!-- Obscure padding between header and side nav bar -->
				<div
					class="absolute -z-0 -top-[1px] -left-[9px] h-[37px] w-4 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
				/>

				<div
					role="columnheader"
					class="sticky left-0 z-[5] flex items-center justify-center px-2 bg-white data-dark:bg-[#42464E] border-r border-[#E4E7EC] data-dark:border-[#333] rounded-l-lg"
				>
					<div
						id="checkbox-bg-obscure"
						class="absolute -z-10 -top-[1px] -left-0 h-[36px] w-full bg-white data-dark:bg-[#42464E] border-l border-t border-b border-[#E4E7EC] data-dark:border-[#333] rounded-l-lg"
					/>

					{#if !readonly}
						<Checkbox
							on:checkedChange={() => {
								if ($genTableRows) {
									return tableState.selectAllRows($genTableRows);
								} else return false;
							}}
							checked={($genTableRows ?? []).every((row) =>
								$tableState.selectedRows.includes(row.ID)
							)}
							class="h-4 sm:h-[18px] w-4 sm:w-[18px] [&>svg]:h-3 sm:[&>svg]:h-3.5 [&>svg]:w-3 sm:[&>svg]:w-3.5 [&>svg]:translate-x-[1px]"
						/>
					{/if}
				</div>

				<ColumnHeader tableType="knowledge" {tableData} {refetchTable} {readonly} />
			</div>

			{#if $genTableRows}
				{#if $genTableRows.length > 0}
					{#each $genTableRows as row}
						<div
							data-streaming={!!$tableState.streamingRows[row.ID] || undefined}
							role="row"
							style="grid-template-columns: 45px {focusedCol === 'ID'
								? '320px'
								: '120px'} {focusedCol === 'Updated at'
								? '320px'
								: '130px'} {$tableState.templateCols};"
							class={cn(
								'relative z-0 grid place-items-start h-min max-h-[100px] sm:max-h-[150px] text-xs sm:text-sm border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-b-[#E4E7EC] data-dark:border-b-[#333] group',
								Object.keys($tableState.colSizes).length !== 0 && 'w-min',
								!$tableState.resizingCol &&
									'transition-[border-color,grid-template-columns] duration-200'
							)}
						>
							<div
								role="gridcell"
								class="sticky z-[1] left-0 flex justify-center px-2 py-1.5 sm:py-2 h-full w-full border-r border-[#E4E7EC] data-dark:border-[#333]"
							>
								<!-- Streaming row colored part -->
								{#if $tableState.streamingRows[row.ID]}
									<div
										class="absolute -z-[1] -top-[1px] -left-[9px] h-[calc(100%_+_2px)] w-1.5 bg-[#F2839F]"
									/>
								{/if}

								<div
									class={cn(
										'absolute -z-10 top-0 -left-4 h-full w-[calc(100%_+_16px)]',
										$tableState.streamingRows[row.ID]
											? 'bg-[#FDEFF4]'
											: 'bg-[#FAFBFC] data-dark:bg-[#1E2024] group-hover:bg-[#ECEDEE]'
									)}
								/>
								{#if !readonly}
									<Checkbox
										on:checkedChange={(e) => handleSelectRow(e, row)}
										checked={!!$tableState.selectedRows.find((i) => i === row.ID)}
										class="mt-[1px] h-4 sm:h-[18px] w-4 sm:w-[18px] [&>svg]:h-3 sm:[&>svg]:h-3.5 [&>svg]:w-3 sm:[&>svg]:w-3.5 [&>svg]:translate-x-[1px]"
									/>
								{/if}
							</div>
							{#each tableData.cols as column}
								{@const editMode =
									$tableState.editingCell &&
									$tableState.editingCell.rowID === row.ID &&
									$tableState.editingCell.columnID === column.id}
								{@const isValidFileUri = isValidUri(row[column.id]?.value)}
								<!-- svelte-ignore a11y-interactive-supports-focus -->
								<div
									data-editing={editMode ? true : undefined}
									role="gridcell"
									tabindex="0"
									on:focusin={() => (focusedCol = column.id)}
									on:focusout={() => (focusedCol = null)}
									on:mousedown={(e) => {
										if (column.id === 'ID' || column.id === 'Updated at') return;

										if (
											(column.dtype === 'file' || column.dtype === 'audio') &&
											row[column.id]?.value &&
											isValidFileUri
										)
											return;
										if (uploadController) return;
										if ($tableState.streamingRows[row.ID] || $tableState.editingCell) return;

										if (e.detail > 1) {
											e.preventDefault();
										}
									}}
									on:dblclick={() => {
										if (readonly) return;
										if (column.id === 'ID' || column.id === 'Updated at') return;

										if (
											(column.dtype === 'file' || column.dtype === 'audio') &&
											row[column.id]?.value &&
											isValidFileUri
										)
											return;
										if (uploadController) return;

										if (!$tableState.streamingRows[row.ID]) {
											tableState.setEditingCell({ rowID: row.ID, columnID: column.id });
										}
									}}
									on:keydown={(e) => {
										if (readonly) return;
										if (column.id === 'ID' || column.id === 'Updated at') return;

										if (
											(column.dtype === 'file' || column.dtype === 'audio') &&
											row[column.id]?.value &&
											isValidFileUri
										)
											return;
										if (uploadController) return;

										if (!editMode && e.key == 'Enter' && !$tableState.streamingRows[row.ID]) {
											tableState.setEditingCell({ rowID: row.ID, columnID: column.id });
										}
									}}
									style={$tableState.columnSettings.column?.id == column.id &&
									$tableState.columnSettings.isOpen
										? 'background-color: #30A8FF17;'
										: ''}
									class={cn(
										'flex flex-col justify-start gap-1 h-full max-h-[99px] sm:max-h-[149px] w-full break-words [&:not(:last-child)]:border-r border-[#E4E7EC] data-dark:border-[#333]',
										editMode
											? 'p-0 bg-black/5 data-dark:bg-white/5'
											: 'p-2 overflow-auto whitespace-pre-line',
										$tableState.streamingRows[row.ID]
											? 'bg-[#FDEFF4]'
											: 'group-hover:bg-[#ECEDEE] data-dark:group-hover:bg-white/5'
									)}
								>
									{#if $tableState.streamingRows[row.ID]?.includes(column.id) && !editMode && column.id !== 'ID' && column.id !== 'Updated at' && column.gen_config}
										<RowStreamIndicator />
									{/if}

									{#if editMode}
										{#if column.dtype === 'file' || column.dtype === 'audio'}
											<FileSelect
												tableType="knowledge"
												controller={uploadController}
												cellToUpdate={{ rowID: row.ID, columnID: column.id }}
												{column}
												{saveEditCell}
											/>
										{:else}
											<!-- svelte-ignore a11y-autofocus -->
											<textarea
												autofocus
												value={row[column.id].value}
												on:keydown={(e) => {
													if (e.key === 'Enter' && !e.shiftKey) {
														e.preventDefault();

														handleSaveEdit(e);
													}
												}}
												class="min-h-[100px] sm:min-h-[150px] h-full w-full p-2 bg-transparent outline outline-secondary resize-none"
											/>
										{/if}
									{:else if column.dtype === 'file' || column.dtype === 'audio'}
										<FileColumnView
											tableType="knowledge"
											rowID={row.ID}
											columnID={column.id}
											fileUri={row[column.id]?.value}
											fileUrl={rowThumbs[row.ID]?.[column.id]?.url}
											bind:isDeletingFile
										/>
									{:else}
										<span
											class="h-min {column.id === 'ID' || column.id === 'Updated at'
												? 'text-[#667085] line-clamp-1 break-all'
												: 'text-text'} whitespace-pre-line"
										>
											{#if column.id === 'ID'}
												{row[column.id]}
											{:else if column.id === 'Updated at'}
												{new Date(row[column.id]).toISOString()}
											{:else}
												{row[column.id]?.value === undefined ? '' : row[column.id]?.value}
											{/if}
										</span>
									{/if}
								</div>
							{/each}
						</div>
					{/each}
				{:else if $genTableRows.length === 0}
					<div
						role="row"
						style="grid-template-columns: 60px {focusedCol === 'ID'
							? '320px'
							: '120px'} {focusedCol === 'Updated at'
							? '320px'
							: '130px'} {$tableState.templateCols};"
						class="sticky top-[40px] z-0 grid place-items-start h-min"
					>
						<div
							role="gridcell"
							class="sticky left-1/2 -translate-x-1/2 flex flex-col items-center justify-center p-1 h-full w-max"
						>
							<NoRowsGraphic class="h-[16rem]" />
							<span class="mt-4 text-base sm:text-lg">Upload Document</span>
							<span class="text-xs sm:text-sm text-[#999]">
								Select a document to start generating your table
							</span>
							<Button on:click={handleUploadClick} class="mt-2 rounded-full pointer-events-auto">
								Browse Document
							</Button>
						</div>
					</div>
				{/if}
			{:else}
				<div class="flex items-center">
					<LoadingSpinner class="sticky left-1/2 h-5 w-5 text-secondary" />
				</div>
			{/if}
		</div>
	</div>
{:else if tableError?.error == 404}
	{#if tableError.message?.org_id && userData?.member_of.find((org) => org.organization_id === tableError.message?.org_id)}
		{@const projectOrg = userData?.member_of.find(
			(org) => org.organization_id === tableError.message?.org_id
		)}
		<FoundProjectOrgSwitcher {projectOrg} message="Table not found" />
	{:else}
		<div class="flex items-center justify-center h-full">
			<p class="font-medium text-xl">Table not found</p>
		</div>
	{/if}
{:else if tableError?.error}
	<div class="flex flex-col items-center justify-center gap-2 self-center h-full max-w-[50%]">
		<p class="font-medium text-xl">{tableError.error} Failed to load table</p>
		<p class="text-sm text-[#999]">{JSON.stringify(tableError.message)}</p>
	</div>
{:else}
	<div class="flex items-center justify-center h-full">
		<LoadingSpinner class="h-5 w-5 text-secondary" />
	</div>
{/if}

<FileThumbsFetch {tableData} bind:rowThumbs />
<DeleteFileDialog
	bind:isDeletingFile
	deleteCb={() => {
		if (isDeletingFile) {
			saveEditCell(isDeletingFile, '');
			delete rowThumbs[isDeletingFile?.rowID][isDeletingFile?.columnID];
			isDeletingFile = null;
		}
	}}
/>
