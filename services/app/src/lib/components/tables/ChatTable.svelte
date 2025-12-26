<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { Maximize2 } from '@lucide/svelte';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import { cn, escapeHtmlText, isValidUri } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableRow, User } from '$lib/types';

	import {
		ColumnHeader,
		DeleteFileDialog,
		FileColumnView,
		FileSelect,
		FileThumbsFetch,
		NewRow
	} from '$lib/components/tables/(sub)';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		user: User | undefined;
		tableData: GenTable | undefined;
		tableError: { error: number; message?: any } | undefined;
		readonly?: boolean;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	}

	let {
		user,
		tableData = $bindable(),
		tableError = $bindable(),
		readonly = false,
		refetchTable
	}: Props = $props();

	let uploadController: AbortController | undefined = undefined;

	//? Expanding ID and Updated at columns
	let focusedCol: string | null = $state(null);

	async function handleSaveEdit(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLTextAreaElement;
		}
	) {
		if (!tableData || !tableRowsState) return;
		if (!tableState.editingCell) return;

		const editedValue = e.currentTarget.value;
		const cellToUpdate = tableState.editingCell;

		await saveEditCell(cellToUpdate, editedValue);
	}

	async function saveEditCell(
		cellToUpdate: { rowID: string; columnID: string },
		editedValue: string
	) {
		if (!tableData || !tableRowsState.rows) return;

		if (
			tableState.showOutputDetails.activeCell?.rowID === cellToUpdate.rowID &&
			tableState.showOutputDetails.activeCell?.columnID === cellToUpdate.columnID
		) {
			tableState.closeOutputDetails();
		}

		//? Optimistic update
		const originalValue = tableRowsState.rows.find((row) => row.ID === cellToUpdate!.rowID)?.[
			cellToUpdate.columnID
		];
		tableRowsState.setCell(cellToUpdate, editedValue);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/rows`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				table_id: tableData.id,
				data: {
					[cellToUpdate.rowID]: {
						[cellToUpdate.columnID]: editedValue
					}
				}
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('CHATTBL_TBL_ROWEDIT', responseBody);
			toast.error('Failed to edit row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			tableRowsState.setCell(cellToUpdate, originalValue?.value);
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
		if (!tableData || !tableRowsState.rows) return;
		//? Select multiple rows with shift key
		const rowIndex = tableRowsState.rows.findIndex(({ ID }) => ID === row.ID);
		if (e.detail.event.shiftKey && tableState.selectedRows.length && shiftOrigin != null) {
			if (shiftOrigin < rowIndex) {
				tableState.setSelectedRows([
					...tableState.selectedRows.filter(
						(i) => !tableRowsState.rows?.some(({ ID }) => ID === i)
					),
					...tableRowsState.rows.slice(shiftOrigin, rowIndex + 1).map(({ ID }) => ID)
				]);
			} else if (shiftOrigin > rowIndex) {
				tableState.setSelectedRows([
					...tableState.selectedRows.filter(
						(i) => !tableRowsState.rows?.some(({ ID }) => ID === i)
					),
					...tableRowsState.rows.slice(rowIndex, shiftOrigin + 1).map(({ ID }) => ID)
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
		if (!tableData || !tableRowsState.rows) return;
		const isCtrl = window.navigator.userAgent.indexOf('Mac') != -1 ? e.metaKey : e.ctrlKey;
		const activeElement = document.activeElement as HTMLElement;
		const isInputActive = activeElement.tagName == 'INPUT' || activeElement.tagName == 'TEXTAREA';
		if (isCtrl && e.key === 'a' && !isInputActive) {
			e.preventDefault();

			if (Object.keys(tableState.streamingRows).length !== 0) return;

			tableState.setSelectedRows([
				...tableState.selectedRows.filter((i) => !tableRowsState.rows?.some(({ ID }) => ID === i)),
				...tableRowsState.rows.map(({ ID }) => ID)
			]);
		}

		if (e.key === 'Escape') {
			tableState.setEditingCell(null);
		}
	}

	//! Unused, for conversations list
	// onDestroy(() => {
	// 	tableRowsState.rows = undefined;
	// 	tableState.reset();
	// });
</script>

<svelte:document
	onmousedown={(e) => {
		const editingCell = document.querySelector('[data-editing="true"]');
		//@ts-ignore
		if (e.target && editingCell && !editingCell.contains(e.target)) {
			tableState.setEditingCell(null);
		}
	}}
	onkeydown={keyboardNavigate}
/>

{#if tableData}
	<div
		data-testid="table-area"
		inert={tableState.columnSettings.isOpen}
		class="flex min-h-0 w-full grow flex-col"
	>
		<div
			onscroll={(e) => {
				//? Used to prevent elements showing through the padding between side nav and table header
				//FIXME: Use transform for performance
				const el = document.getElementById('checkbox-bg-obscure');
				if (el) {
					el.style.left = `-${e.currentTarget.scrollLeft > 20 ? 20 : e.currentTarget.scrollLeft}px`;
				}
			}}
			role="grid"
			style="grid-template-rows: 36px {tableRowsState.rows && !tableRowsState.loading
				? `repeat(${tableRowsState.rows.length + (!readonly ? 1 : 0)}, min-content)`
				: 'minmax(0, 1fr)'};"
			class="relative grid grow overflow-auto px-2"
		>
			<div
				role="row"
				style="grid-template-columns: 45px {focusedCol === 'ID' ? '320px' : '120px'} {focusedCol ===
				'Updated at'
					? '320px'
					: '130px'} {tableState.templateCols} {tableState.addingCol ? 'minmax(320px, 1fr)' : ''};"
				class={cn(
					'sticky top-0 z-20 grid h-[36px] rounded-lg border border-[#E4E7EC] bg-white text-xs data-dark:border-[#333] data-dark:bg-[#42464E] sm:text-sm',
					Object.keys(tableState.colSizes).length !== 0 && 'w-min',
					!tableState.resizingCol && 'transition-[grid-template-columns] duration-200'
				)}
			>
				<!-- Obscure padding between header and side nav bar -->
				<div
					class="absolute -left-[9px] -top-[1px] -z-0 h-[37px] w-4 bg-[#F2F4F7] data-dark:bg-[#1E2024]"
				></div>

				<div
					role="columnheader"
					class="sticky left-0 z-[5] flex items-center justify-center rounded-l-lg border-r border-[#E4E7EC] bg-white px-2 data-dark:border-[#333] data-dark:bg-[#42464E]"
				>
					<div
						id="checkbox-bg-obscure"
						class="absolute -left-0 -top-[1px] -z-10 h-[36px] w-full rounded-l-lg border-b border-l border-t border-[#E4E7EC] bg-white data-dark:border-[#333] data-dark:bg-[#42464E]"
					></div>

					{#if !readonly}
						<Checkbox
							on:checkedChange={() => {
								if (tableRowsState.rows) {
									return tableState.selectAllRows(tableRowsState.rows);
								} else return false;
							}}
							checked={(tableRowsState.rows ?? []).every((row) =>
								tableState.selectedRows.includes(row.ID)
							)}
							class="h-4 w-4 sm:h-[18px] sm:w-[18px] [&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[1px] sm:[&>svg]:h-3.5 sm:[&>svg]:w-3.5"
						/>
					{/if}
				</div>

				<ColumnHeader tableType="chat" {tableData} {refetchTable} {readonly} />
			</div>

			{#if tableRowsState.rows && !tableRowsState.loading}
				{#if !readonly}
					<NewRow
						tableType="chat"
						{tableData}
						{focusedCol}
						{refetchTable}
						class={cn(
							Object.keys(tableState.colSizes).length !== 0 && 'w-min',
							!tableState.resizingCol &&
								'transition-[border-color,grid-template-columns] duration-200'
						)}
					/>
				{/if}

				<!-- Bandaid fix for no scrolling when no rows -->
				<div
					style="grid-template-columns: 45px 120px 130px {tableState.templateCols};"
					class="pointer-events-none invisible z-0 grid h-0 place-items-start"
				></div>

				{#each tableRowsState.rows as row}
					<div
						data-streaming={!!tableState.streamingRows[row.ID] || undefined}
						role="row"
						style="grid-template-columns: 45px {focusedCol === 'ID'
							? '320px'
							: '120px'} {focusedCol === 'Updated at'
							? '320px'
							: '130px'} {tableState.templateCols} {tableState.addingCol
							? 'minmax(320px, 1fr)'
							: ''};"
						class={cn(
							'group relative z-0 grid h-min max-h-[100px] place-items-start border-b border-l border-r border-b-[#E4E7EC] border-l-transparent border-r-transparent text-xs data-dark:border-b-[#333] data-dark:border-l-transparent data-dark:border-r-transparent sm:max-h-[150px] sm:text-sm',
							Object.keys(tableState.colSizes).length !== 0 && 'w-min',
							!tableState.resizingCol &&
								'transition-[border-color,grid-template-columns] duration-200'
						)}
					>
						<div
							role="gridcell"
							class="sticky left-0 z-[1] flex h-full w-full justify-center border-r border-[#E4E7EC] px-2 py-1.5 data-dark:border-[#333] sm:py-2"
						>
							<!-- Streaming row colored part -->
							{#if tableState.streamingRows[row.ID]}
								<div
									class="absolute -left-[9px] -top-[1px] -z-[1] h-[calc(100%_+_2px)] w-1.5 bg-[#F2839F]"
								></div>
							{/if}

							<div
								class={cn(
									'absolute -left-4 top-0 -z-10 h-full w-[calc(100%_+_16px)]',
									tableState.streamingRows[row.ID]
										? 'bg-[#FDEFF4]'
										: 'bg-[#F2F4F7] group-hover:bg-[#E7EBF1] data-dark:bg-[#1E2024]'
								)}
							></div>
							{#if !readonly}
								<Checkbox
									on:checkedChange={(e) => handleSelectRow(e, row)}
									checked={!!tableState.selectedRows.find((i) => i === row.ID)}
									class="mt-[1px] h-4 w-4 sm:h-[18px] sm:w-[18px] [&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[1px] sm:[&>svg]:h-3.5 sm:[&>svg]:w-3.5"
								/>
							{/if}
						</div>
						{#each tableData.cols as column}
							{@const editMode =
								tableState.editingCell &&
								tableState.editingCell.rowID === row.ID &&
								tableState.editingCell.columnID === column.id}
							{@const isValidFileUri = isValidUri(row[column.id]?.value)}
							<!-- svelte-ignore a11y_interactive_supports_focus -->
							<div
								data-row-id={escapeHtmlText(row.ID)}
								data-col-id={escapeHtmlText(column.id)}
								data-editing={editMode ? true : undefined}
								role="gridcell"
								tabindex="0"
								onfocusin={() => (focusedCol = column.id)}
								onfocusout={() => (focusedCol = null)}
								onmousedown={(e) => {
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (
										(column.dtype === 'image' ||
											column.dtype === 'audio' ||
											column.dtype === 'document') &&
										row[column.id]?.value &&
										isValidFileUri
									)
										return;
									if (uploadController) return;
									if (tableState.streamingRows[row.ID] || tableState.editingCell) return;

									if (e.detail > 1) {
										e.preventDefault();
									}
								}}
								ondblclick={() => {
									if (readonly) return;
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (
										(column.dtype === 'image' ||
											column.dtype === 'audio' ||
											column.dtype === 'document') &&
										row[column.id]?.value &&
										isValidFileUri
									)
										return;
									if (uploadController) return;

									if (!tableState.streamingRows[row.ID]) {
										tableState.setEditingCell({ rowID: row.ID, columnID: column.id });
									}
								}}
								onkeydown={(e) => {
									if (readonly) return;
									if (column.id === 'ID' || column.id === 'Updated at') return;

									if (
										(column.dtype === 'image' ||
											column.dtype === 'audio' ||
											column.dtype === 'document') &&
										row[column.id]?.value &&
										isValidFileUri
									)
										return;
									if (uploadController) return;

									if (!editMode && e.key == 'Enter' && !tableState.streamingRows[row.ID]) {
										tableState.setEditingCell({ rowID: row.ID, columnID: column.id });
									}
								}}
								style={tableState.columnSettings.column?.id == column.id &&
								tableState.columnSettings.isOpen
									? 'background-color: #30A8FF17;'
									: ''}
								class={cn(
									'group/cell relative flex h-full max-h-[99px] w-full flex-col justify-start gap-1 break-words border-[#E4E7EC] data-dark:border-[#333] sm:max-h-[149px] [&:not(:last-child)]:border-r',
									editMode ? 'bg-black/5 p-0 data-dark:bg-white/5' : '',
									tableState.streamingRows[row.ID]
										? 'bg-[#FDEFF4]'
										: 'group-hover:bg-[#E7EBF1] data-dark:group-hover:bg-white/5'
								)}
							>
								{#if tableState.streamingRows[row.ID]?.includes(column.id) && !editMode && column.id !== 'ID' && column.id !== 'Updated at' && column.gen_config}
									<div class="flex items-center gap-2 p-2">
										<RowStreamIndicator />

										{#if row[column.id]?.reasoning_content && !row[column.id]?.value && tableState.streamingRows[row.ID]?.includes(column.id)}
											<span class="text-xs font-medium text-[#98A2B3]">Thinking...</span>
										{/if}
									</div>
								{/if}

								{#if row[column.id]?.reasoning_content && !row[column.id]?.value && tableState.streamingRows[row.ID]?.includes(column.id)}
									<p
										data-reasoning-text
										class="h-min overflow-auto whitespace-pre-line p-2 text-[#98A2B3]"
									>
										{row[column.id]?.reasoning_content}
									</p>
								{/if}

								{#if editMode}
									{#if column.dtype === 'image' || column.dtype === 'audio' || column.dtype === 'document'}
										<FileSelect
											tableType="chat"
											controller={uploadController}
											cellToUpdate={{ rowID: row.ID, columnID: column.id }}
											{column}
											{saveEditCell}
										/>
									{:else}
										<!-- svelte-ignore a11y_autofocus -->
										<textarea
											autofocus
											value={row[column.id].value}
											onkeydown={(e) => {
												if (e.key === 'Enter' && !e.shiftKey) {
													e.preventDefault();

													handleSaveEdit(e);
												}
											}}
											class="h-full min-h-[100px] w-full resize-none bg-transparent p-2 outline outline-secondary sm:min-h-[150px]"
										></textarea>
									{/if}
								{:else if column.dtype === 'image' || column.dtype === 'audio' || column.dtype === 'document'}
									<FileColumnView
										tableType="chat"
										{readonly}
										rowID={row.ID}
										columnID={column.id}
										fileUri={row[column.id]?.value}
										fileUrl={tableState.rowThumbs[row.ID]?.[column.id]?.url}
									/>
								{:else}
									{#if !(!row[column.id]?.value && tableState.streamingRows[row.ID]?.includes(column.id))}
										<p
											class="h-min {column.id === 'ID' || column.id === 'Updated at'
												? 'm-2 line-clamp-1 break-all text-[#667085]'
												: 'overflow-auto p-2 text-text'} whitespace-pre-line"
										>
											{#if column.id === 'ID'}
												{row[column.id]}
											{:else if column.id === 'Updated at'}
												{new Date(row[column.id]).toISOString()}
											{:else}
												{row[column.id]?.value === undefined ? '' : row[column.id]?.value}
											{/if}
										</p>
									{/if}

									{#if column.dtype === 'str'}
										<div
											class="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-focus-within/cell:opacity-100 group-hover/cell:opacity-100"
										>
											<Button
												variant="ghost"
												onclick={() => {
													tableState.showOutputDetails = {
														open: true,
														activeCell: { rowID: row.ID, columnID: column.id },
														activeTab:
															tableState.streamingRows[row.ID]?.includes(column.id) &&
															!row[column.id]?.value
																? 'thinking'
																: 'answer',
														message: {
															content: row[column.id]?.value,
															chunks: row[column.id]?.references?.chunks ?? []
														},
														reasoningContent: row[column.id]?.reasoning_content ?? null,
														reasoningTime: row[column.id]?.reasoning_time ?? null,
														expandChunk: null,
														preview: null
													};
												}}
												title="Show output details"
												class="aspect-square h-6 rounded-md bg-white p-0 text-[#667085] hover:text-[#667085]"
											>
												<Maximize2 class="h-3.5 w-3.5" />
											</Button>
										</div>
									{/if}
								{/if}
							</div>
						{/each}
					</div>
				{/each}
			{:else}
				<div class="flex items-center">
					<LoadingSpinner class="sticky left-1/2 h-5 w-5 text-secondary" />
				</div>
			{/if}
		</div>
	</div>
{:else if tableError?.error == 404}
	{#if tableError.message?.org_id && user?.org_memberships.find((org) => org.organization_id === tableError.message?.org_id)}
		{@const projectOrg = user?.organizations.find((org) => org.id === tableError.message?.org_id)}
		<FoundProjectOrgSwitcher {projectOrg} message="Table not found" />
	{:else}
		<div class="flex h-full items-center justify-center">
			<p class="text-xl font-medium">Table not found</p>
		</div>
	{/if}
{:else if tableError?.error}
	<div class="flex h-full max-w-[80%] flex-col items-center justify-center gap-2 self-center">
		<p class="text-xl font-medium">{tableError.error} Failed to load table</p>
		<p class="break-all text-sm text-[#999]">
			{tableError.message.message ?? JSON.stringify(tableError.message)}
		</p>
	</div>
{:else}
	<div class="flex h-full items-center justify-center">
		<LoadingSpinner class="h-5 w-5 text-secondary" />
	</div>
{/if}

<FileThumbsFetch {tableData} />
<DeleteFileDialog
	deleteCb={() => {
		if (tableState.deletingFile) {
			saveEditCell(tableState.deletingFile, '');
			delete tableState.rowThumbs[tableState.deletingFile?.rowID][
				tableState.deletingFile?.columnID
			];
			tableState.deletingFile = null;
		}
	}}
/>
