<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { v4 as uuidv4 } from 'uuid';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { genTableDTypes, jamaiApiVersion, tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import InputText from '$lib/components/InputText.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import Portal from '$lib/components/Portal.svelte';
	import DraggableList from '$lib/components/DraggableList.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';

	export let isAddingTable: boolean;

	const LLM_GEN_CONFIG_DEFAULT = {
		object: 'gen_config.llm',
		model: '',
		system_prompt: '',
		prompt: '',
		temperature: 1,
		max_tokens: 1000,
		top_p: 0.1
	} as const;
	const CODE_GEN_CONFIG_DEFAULT = {
		object: 'gen_config.code',
		source_column: ''
	} as const;

	let tableId = '';
	let columns: (Omit<GenTableCol, 'vlen' | 'config'> & { drag_id: string })[] = []; //? Added drag_id to keep track of dragging

	let isLoading = false;

	$: if (!isAddingTable) {
		tableId = '';
		columns = [];
	}

	async function handleAddTable() {
		if (!tableId) return toast.error('Table ID is required', { id: 'table-id-req' });
		if (columns.find((col) => !col.id))
			return toast.error('Column ID cannot be empty', { id: 'column-id-req' });

		if (!tableIDPattern.test(tableId))
			return toast.error(
				'Table ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'table-id-invalid' }
			);

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				id: tableId,
				version: jamaiApiVersion,
				cols: columns.map((col) => ({
					...col,
					dtype: col.dtype.replace('_code', ''),
					drag_id: undefined
				}))
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
			goto(`/project/${$page.params.project_id}/action-table/${responseBody.id}`);
		}
	}
</script>

<Dialog.Root bind:open={isAddingTable}>
	<Dialog.Content data-testid="new-table-dialog" class="max-h-[90vh] w-[clamp(0px,45rem,100%)]">
		<Dialog.Header>New action table</Dialog.Header>

		<div class="grow w-full overflow-auto">
			<div
				class="flex items-center gap-3 px-4 sm:px-6 py-3 w-full text-center border-b border-[#E5E5E5] data-dark:border-[#484C55]"
			>
				<span class="whitespace-nowrap font-medium text-left text-xs sm:text-sm text-black">
					Table ID*
				</span>

				<InputText bind:value={tableId} name="table_id" placeholder="Required" />
			</div>

			<div class="px-4 sm:px-6 pt-3">
				<h3 class="font-medium">Columns</h3>

				{#if columns.length === 0}
					<p class="py-6 text-center text-sm text-black">No columns added</p>
				{:else}
					<div
						class="mt-3 p-2 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#F2F4F7] rounded-lg"
					>
						<div
							style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px;"
							class="grid gap-2 mb-1"
						>
							<span></span>

							<span class="ml-1 font-medium text-left text-xs sm:text-sm text-black">
								Column ID*
							</span>

							<span class="ml-1 font-medium text-left text-xs sm:text-sm text-black">
								Data Type*
							</span>

							<span class="ml-1 font-medium text-left text-xs sm:text-sm text-black">
								Output*
							</span>

							<span></span>
						</div>

						<DraggableList tagName="ul" bind:itemList={columns}>
							<svelte:fragment
								slot="list-item"
								let:item={column}
								let:itemIndex={index}
								let:dragStart
								let:dragMove
								let:dragOver
								let:dragEnd
								let:draggingItem={draggingColumn}
							>
								<li
									on:dragover={(e) => dragOver(e, index)}
									style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px;"
									class="grid gap-2 {draggingColumn?.drag_id == column.drag_id ? 'opacity-0' : ''}"
								>
									<button
										title="Drag to reorder columns"
										on:dragstart={(e) => dragStart(e, column, index)}
										on:drag={dragMove}
										on:dragend={dragEnd}
										on:touchstart={(e) => dragStart(e, column, index)}
										on:touchmove={dragMove}
										on:touchend={dragEnd}
										draggable={true}
										class="flex items-center justify-center cursor-grab touch-none"
									>
										<HamburgerIcon class="h-5" />
									</button>

									<div class="flex flex-col gap-2 py-1 w-full text-center">
										<InputText
											bind:value={columns[index].id}
											placeholder="Required"
											class="bg-white data-dark:bg-[#42464e]"
										/>
									</div>

									<div class="flex flex-col gap-2 py-1 w-full text-center">
										<Select.Root
											selected={{ value: columns[index].dtype }}
											onSelectedChange={(v) => {
												if (v) {
													columns[index].dtype = v.value;
													if (columns[index].gen_config) {
														columns[index].gen_config = v.value.endsWith('_code')
															? CODE_GEN_CONFIG_DEFAULT
															: LLM_GEN_CONFIG_DEFAULT;
													}
												}
											}}
										>
											<Select.Trigger asChild let:builder>
												<Button
													builders={[builder]}
													variant="outline-neutral"
													class="flex items-center justify-between gap-2 sm:gap-8 pl-3 pr-2 h-[38px] min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] border-transparent rounded-md"
												>
													<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
														{genTableDTypes[column.dtype]
															? genTableDTypes[column.dtype]
															: 'Select Data Type'}
													</span>

													<ChevronDown class="h-4 w-4" />
												</Button>
											</Select.Trigger>
											<Select.Content side="left" class="max-h-64 overflow-y-auto">
												{#each Object.keys(genTableDTypes).filter((dtype) => (column.gen_config || !dtype.endsWith('_code')) && (!column.gen_config || dtype.startsWith('str') || dtype === 'file_code')) as dType}
													<Select.Item
														value={dType}
														label={genTableDTypes[dType]}
														class="flex justify-between gap-10 cursor-pointer"
													>
														{genTableDTypes[dType]}
													</Select.Item>
												{/each}
											</Select.Content>
										</Select.Root>
									</div>

									<div class="flex items-center justify-center">
										<Checkbox
											on:checkedChange={(e) => {
												if (e.detail.value) {
													columns[index].gen_config = columns[index].dtype.endsWith('_code')
														? CODE_GEN_CONFIG_DEFAULT
														: LLM_GEN_CONFIG_DEFAULT;

													if (!['str', 'image'].includes(columns[index].dtype)) {
														columns[index].dtype = 'str';
													}
												} else {
													columns[index].gen_config = null;

													if (columns[index].dtype.endsWith('_code')) {
														columns[index].dtype = 'str';
													}
												}
											}}
											checked={!!column.gen_config}
											class="h-5 w-5 [&>svg]:translate-x-[1px]"
										/>
									</div>

									<Button
										variant="ghost"
										title="Remove column"
										on:click={() => (columns = columns.filter((_, idx) => index !== idx))}
										class="p-0 h-8 w-8 aspect-square rounded-full place-self-center"
									>
										<CloseIcon class="h-5" />
									</Button>
								</li>
							</svelte:fragment>

							<svelte:fragment
								slot="dragged-item"
								let:dragMouseCoords
								let:draggingItem={draggingColumn}
							>
								{#if dragMouseCoords && draggingColumn}
									<Portal>
										<li
											inert
											style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px; top: {dragMouseCoords.y -
												dragMouseCoords.startY -
												10}px; left: {dragMouseCoords.x -
												dragMouseCoords.startX}px; width: {dragMouseCoords.width}px;"
											class="fixed z-[9999] grid gap-2 mt-3 bg-[#F4F5FA] data-dark:bg-[#42464e] pointer-events-none"
										>
											<button class="flex items-center justify-center cursor-grab">
												<HamburgerIcon class="h-5" />
											</button>

											<div class="flex flex-col gap-2 py-1 w-full text-center">
												<InputText
													placeholder="Required"
													value={draggingColumn.id}
													class="bg-white data-dark:bg-[#42464e]"
												/>
											</div>

											<div class="flex flex-col gap-2 py-1 w-full text-center">
												<Button
													variant="outline-neutral"
													class="flex items-center justify-between gap-2 sm:gap-8 pl-3 pr-2 h-[38px] min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
												>
													<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
														{draggingColumn.dtype ? draggingColumn.dtype : 'Select Data Type'}
													</span>

													<ChevronDown class="h-4 w-4" />
												</Button>
											</div>

											<div class="flex items-center justify-center">
												<Checkbox checked={!!draggingColumn.gen_config} class="h-5 w-5" />
											</div>

											<Button
												variant="ghost"
												class="p-0 h-8 w-8 aspect-square rounded-full place-self-center"
											>
												<CloseIcon class="h-5" />
											</Button>
										</li>
									</Portal>
								{/if}
							</svelte:fragment>
						</DraggableList>
					</div>
				{/if}
			</div>

			<div class="mt-3 px-4 sm:px-6 pb-3">
				<Button
					variant="outline"
					on:click={() =>
						(columns = [
							...columns,
							{ id: '', dtype: 'str', drag_id: uuidv4(), index: false, gen_config: null }
						])}
					class="flex items-center justify-center gap-2 h-10 w-full text-sm border-dashed rounded-lg"
				>
					<AddIcon class="h-4 w-4" />
					Add column
				</Button>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleAddTable}
					type="button"
					disabled={isLoading}
					loading={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
