<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { v4 as uuidv4 } from 'uuid';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import {
		genTableColDTypes,
		genTableColTypes,
		genTableDTypes,
		jamaiApiVersion,
		tableIDPattern
	} from '$lib/constants';
	import logger from '$lib/logger';
	import type { EmbedGenConfig, GenTableCol } from '$lib/types';

	import InputText from '$lib/components/InputText.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import Portal from '$lib/components/Portal.svelte';
	import DraggableList from '$lib/components/DraggableList.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';

	const newColDefault = () => ({
		id: '',
		col_type: null,
		dtype: '',
		gen_config: null,
		drag_id: uuidv4(),
		index: false
	});

	interface Props {
		isAddingTable: boolean;
	}

	let { isAddingTable = $bindable() }: Props = $props();

	let tableId = $state('');
	let columns: (Omit<GenTableCol, 'vlen' | 'config'> & {
		gen_config: Exclude<GenTableCol['gen_config'], EmbedGenConfig>;
		col_type: keyof typeof genTableColTypes | null;
		drag_id: string;
	})[] = $state([newColDefault()]); //? Added drag_id to keep track of dragging

	let isLoading = $state(false);

	$effect(() => {
		if (!isAddingTable) {
			tableId = '';
			columns = [newColDefault()];
		}
	});

	async function handleAddTable() {
		if (!tableId) return toast.error('Table ID is required', { id: 'table-id-req' });
		if (columns.slice(0, -1).find((col) => !col?.id))
			return toast.error('Column ID cannot be empty', { id: 'column-id-req' });

		if (!tableIDPattern.test(tableId))
			return toast.error(
				'Table ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'table-id-invalid' }
			);

		const invalidCodeColumns = columns
			.slice(0, -1)
			.filter(
				(column, i) =>
					column.col_type === 'Code Output' &&
					!columns.slice(0, i).findLast((col) => col.dtype === 'str')?.id
			);
		if (invalidCodeColumns.length > 0) {
			return toast.error(
				`No valid source column found for column(s): ${invalidCodeColumns.map((col) => col.id).join(', ')}`,
				{ id: 'code-column-no-source' }
			);
		}

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/action`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id
			},
			body: JSON.stringify({
				id: tableId,
				version: jamaiApiVersion,
				cols: columns
					.map((col, i) => {
						if (col.col_type === 'Code Output') {
							return {
								...col,
								col_type: undefined,
								drag_id: undefined,
								gen_config: {
									...col.gen_config,
									source_column:
										columns.slice(0, i).findLast((col) => col.dtype === 'str')?.id ?? ''
								}
							};
						} else if (col.col_type === 'Python Output') {
							return {
								...col,
								col_type: undefined,
								drag_id: undefined,
								gen_config: {
									...col.gen_config,
									python_code: `row["${col.id}"] = "<result here>"`
								}
							};
						} else {
							return {
								...col,
								col_type: undefined,
								drag_id: undefined
							};
						}
					})
					.slice(0, -1)
			})
		});

		const responseBody = await response.json();
		if (!response.ok) {
			logger.error('ACTIONTBL_TBL_ADD', responseBody);
			toast.error('Failed to add table', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			isLoading = false;
		} else {
			goto(`/project/${page.params.project_id}/action-table/${responseBody.id}`);
		}
	}
</script>

<Dialog.Root bind:open={isAddingTable}>
	<Dialog.Content data-testid="new-table-dialog" class="max-h-[90vh] w-[clamp(0px,50rem,100%)]">
		<Dialog.Header>New action table</Dialog.Header>

		<div class="w-full grow overflow-auto [scrollbar-gutter:stable]">
			<div class="flex w-full items-center gap-3 px-4 py-3 text-center sm:px-5">
				<Label required class="whitespace-nowrap text-xs sm:text-sm">Table Name</Label>

				<InputText bind:value={tableId} name="table_id" placeholder="Required" />
			</div>

			<div class="px-4 pt-3 sm:px-5">
				<h3 class="font-medium">Table Columns</h3>

				<div
					class="mt-3 rounded-lg border border-[#F2F4F7] bg-[#F4F5FA] p-2 data-dark:bg-[#42464e]"
				>
					<div
						style="grid-template-columns: 30px minmax(0, 1.2fr) repeat(2, minmax(0, 1fr)) 40px;"
						class="mb-1 grid gap-2 text-[#98A2B3]"
					>
						<span></span>

						<Label required class="ml-1 whitespace-nowrap text-xs sm:text-sm">Name</Label>

						<Label required class="ml-1 whitespace-nowrap text-xs sm:text-sm">Column Type</Label>

						<Label required class="ml-1 whitespace-nowrap text-xs sm:text-sm">Data Type</Label>

						<span></span>
					</div>

					<DraggableList tagName="ul" bind:itemList={columns}>
						{#snippet listItem({
							item: column,
							itemIndex: index,
							dragStart,
							dragMove,
							dragOver,
							dragEnd,
							draggingItem: draggingColumn
						})}
							<li
								ondragover={(e) => (columns.length === index + 1 ? null : dragOver(e, index))}
								style="grid-template-columns: 30px minmax(0, 1.2fr) repeat(2, minmax(0, 1fr)) auto;"
								class="grid gap-2 {draggingColumn?.drag_id == column.drag_id ? 'opacity-0' : ''}"
							>
								<button
									title="Drag to reorder columns"
									ondragstart={(e) => dragStart(e, column, index)}
									ondrag={dragMove}
									ondragend={dragEnd}
									ontouchstart={(e) => dragStart(e, column, index)}
									ontouchmove={dragMove}
									ontouchend={dragEnd}
									draggable={true}
									class:invisible={columns.length === index + 1}
									class="flex cursor-grab touch-none items-center justify-center"
								>
									<HamburgerIcon class="h-5 text-[#667085]" />
								</button>

								<div class="flex w-full flex-col gap-2 py-1 text-center">
									<InputText
										bind:value={columns[index].id}
										oninput={() => {
											if (columns.length === index + 1) {
												if (columns[index].col_type === null) columns[index].col_type = 'Input';
												columns[index].dtype =
													'str' /* genTableColDTypes[column.col_type ?? 'Input'][0] */;
												columns = [...columns, newColDefault()];
											}
										}}
										placeholder="New column"
										class="h-[38px] border border-[#E4E7EC] {columns.length === index + 1
											? 'bg-[#F9FAFB]'
											: 'bg-white data-dark:bg-[#42464e]'}"
									/>
								</div>

								<div class="flex w-full flex-col gap-2 py-1 text-center">
									<Select.Root
										type="single"
										value={columns[index].col_type ?? undefined}
										onValueChange={(v) => {
											columns[index].col_type = v as keyof typeof genTableColTypes;
											columns[index].gen_config = genTableColTypes[columns[index].col_type];
											if (
												!genTableColDTypes[column.col_type ?? 'Input'].includes(
													columns[index].dtype
												)
											) {
												columns[index].dtype =
													'str' /* genTableColDTypes[column.col_type ?? 'Input'][0] */;
											}

											if (columns.length === index + 1) {
												columns = [...columns, newColDefault()];
											}
										}}
									>
										<Select.Trigger
											class="flex h-[38px] min-w-full items-center justify-between gap-2 border border-[#E4E7EC] pl-3 pr-2 data-dark:hover:bg-white/[0.1] sm:gap-8 {columns.length ===
											index + 1
												? 'bg-[#F9FAFB]'
												: 'bg-white pl-3 pr-2 data-dark:bg-[#0D0E11]'}"
										>
											{#snippet children()}
												<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
													{column.col_type || 'Select column type'}
												</span>
											{/snippet}
										</Select.Trigger>
										<Select.Content side="left" class="max-h-64 overflow-y-auto">
											{#each Object.keys(genTableColTypes) as colType}
												<Select.Item
													value={colType}
													label={colType}
													class="flex cursor-pointer justify-between gap-10"
												>
													{colType}
												</Select.Item>
											{/each}
										</Select.Content>
									</Select.Root>
								</div>

								<div class="flex w-full flex-col gap-2 py-1 text-center">
									<Select.Root
										type="single"
										value={columns[index].dtype}
										onValueChange={(v) => {
											columns[index].dtype = v;

											if (columns.length === index + 1) {
												columns[index].col_type = (Object.entries(genTableColDTypes).find(
													([colType, dTypes]) => dTypes.includes(v)
												)?.[0] ?? 'Input') as keyof typeof genTableColDTypes;
												columns = [...columns, newColDefault()];
											}
										}}
									>
										<Select.Trigger
											class="flex h-[38px] min-w-full items-center justify-between gap-2 border border-[#E4E7EC] pl-3 pr-2 data-dark:hover:bg-white/[0.1] sm:gap-8 {columns.length ===
											index + 1
												? 'bg-[#F9FAFB]'
												: 'bg-white data-dark:bg-[#0D0E11]'}"
										>
											{#snippet children()}
												<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
													{genTableDTypes[column.dtype] || 'Select data type'}
												</span>
											{/snippet}
										</Select.Trigger>
										<Select.Content side="left" class="max-h-64 overflow-y-auto">
											{#each genTableColDTypes[column.col_type ?? 'Input'] as dType}
												<Select.Item
													value={dType}
													label={genTableDTypes[dType]}
													class="flex cursor-pointer justify-between gap-10"
												>
													{genTableDTypes[dType]}
												</Select.Item>
											{/each}
										</Select.Content>
									</Select.Root>
								</div>

								<Button
									variant="ghost"
									title="Remove column"
									onclick={() => (columns = columns.filter((_, idx) => index !== idx))}
									class="aspect-square h-8 w-8 place-self-center rounded-full p-0 {columns.length ===
									index + 1
										? 'invisible'
										: ''}"
								>
									<CloseIcon class="h-5 text-[#475467]" />
								</Button>
							</li>
						{/snippet}

						{#snippet draggedItem({ dragMouseCoords, draggingItem: draggingColumn })}
							<Portal>
								{#if dragMouseCoords && draggingColumn}
									<li
										inert
										style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px; top: {dragMouseCoords.y -
											dragMouseCoords.startY -
											10}px; left: {dragMouseCoords.x -
											dragMouseCoords.startX}px; width: {dragMouseCoords.width}px;"
										class="pointer-events-none fixed z-[9999] mt-3 grid gap-2 bg-[#F4F5FA] data-dark:bg-[#42464e]"
									>
										<button class="flex cursor-grab items-center justify-center">
											<HamburgerIcon class="h-5" />
										</button>

										<div class="flex w-full flex-col gap-2 py-1 text-center">
											<InputText
												placeholder="Required"
												value={draggingColumn.id}
												class="bg-white data-dark:bg-[#42464e]"
											/>
										</div>

										<div class="flex w-full flex-col gap-2 py-1 text-center">
											<Button
												variant="outline-neutral"
												class="flex h-[38px] min-w-full items-center justify-between gap-2 rounded-md border-transparent bg-white pl-3 pr-2 data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] sm:gap-8"
											>
												<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
													{genTableDTypes[draggingColumn.dtype]
														? genTableDTypes[draggingColumn.dtype]
														: 'Select Data Type'}
												</span>

												<ChevronDown class="h-4 w-4" />
											</Button>
										</div>

										<div class="flex items-center justify-center">
											<Checkbox checked={!!draggingColumn.gen_config} class="h-5 w-5" />
										</div>

										<Button
											variant="ghost"
											class="aspect-square h-8 w-8 place-self-center rounded-full p-0"
										>
											<CloseIcon class="h-5" />
										</Button>
									</li>
								{/if}
							</Portal>
						{/snippet}
					</DraggableList>
				</div>
			</div>

			<!-- <div class="mt-3 px-4 pb-3 sm:px-6">
				<Button
					variant="outline"
					onclick={() =>
						(columns = [
							...columns,
							{
								id: '',
								dtype: 'str',
								drag_id: uuidv4(),
								index: false,
								gen_config: null,
								col_type: 'Input'
							}
						])}
					class="flex h-10 w-full items-center justify-center gap-2 rounded-lg border-dashed text-sm"
				>
					<AddIcon class="h-4 w-4" />
					Add column
				</Button>
			</div> -->
		</div>

		<Dialog.Actions class="mt-2 border-0">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					onclick={handleAddTable}
					type="button"
					disabled={isLoading}
					loading={isLoading}
					class="relative grow px-6"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
