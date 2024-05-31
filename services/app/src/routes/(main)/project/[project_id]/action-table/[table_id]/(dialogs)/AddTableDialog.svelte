<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { v4 as uuidv4 } from 'uuid';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import autoAnimate from '@formkit/auto-animate';
	import { pastActionTables } from '../../actionTablesStore';
	import { actionTableDTypes } from '$lib/constants';
	import logger from '$lib/logger';
	import type { ActionTableCol } from '$lib/types';

	import Checkbox from '$lib/components/Checkbox.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let isAddingTable: boolean;

	let tableId = '';
	let columns: (Omit<ActionTableCol, 'vlen' | 'config'> & { drag_id: string })[] = []; //? Added drag_id to keep track of dragging

	let isLoading = false;

	$: if (!isAddingTable) {
		tableId = '';
		columns = [];
	}

	//? Reorder columns
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = null;
	let draggingColumn: (Omit<ActionTableCol, 'vlen' | 'config'> & { drag_id: string }) | null = null;
	let draggingColumnIndex: number | null = null;
	let hoveredColumnIndex: number | null = null;

	$: if (
		draggingColumnIndex != null &&
		hoveredColumnIndex != null &&
		draggingColumnIndex != hoveredColumnIndex
	) {
		[columns[draggingColumnIndex], columns[hoveredColumnIndex]] = [
			columns[hoveredColumnIndex],
			columns[draggingColumnIndex]
		];

		draggingColumnIndex = hoveredColumnIndex;
	}

	async function handleAddTable() {
		if (!tableId) return alert('Table ID is required');

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				id: tableId,
				cols: columns.map((col) => ({ ...col, drag_id: undefined }))
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_TBL_ADD', responseBody);
			alert('Failed to add table: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			//TODO: Consider invalidating fetch request instead
			$pastActionTables = [
				{
					id: tableId,
					cols: [],
					lock_till: 0,
					updated_at: new Date().toISOString(),
					indexed_at_fts: null,
					indexed_at_sca: null,
					indexed_at_vec: null,
					parent_id: null,
					title: ''
				},
				...$pastActionTables
			];
			isAddingTable = false;
			tableId = '';
			columns = [];
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={isAddingTable}>
	<Dialog.Content class="max-h-[90vh] min-w-[45rem]">
		<Dialog.Header>Create New Action Table</Dialog.Header>

		<div class="grow w-full overflow-auto">
			<div
				class="flex items-center gap-4 px-8 py-4 w-full text-center border-b border-[#E5E5E5] data-dark:border-[#484C55]"
			>
				<span
					class="whitespace-nowrap font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
				>
					Table ID
				</span>

				<input
					type="text"
					bind:value={tableId}
					class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<div class="px-8 pt-4">
				<h3 class="font-medium">Columns</h3>

				{#if columns.length === 0}
					<p class="py-6 text-center text-sm text-[#999] data-dark:text-[#C9C9C9]">
						No columns added
					</p>
				{:else}
					<div class="mt-3 p-2 bg-[#F4F5FA] data-dark:bg-[#42464e] rounded-lg">
						<div
							style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px;"
							class="grid gap-2"
						>
							<span></span>

							<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								Column ID
							</span>

							<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								Data Type
							</span>

							<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								Output
							</span>

							<span></span>
						</div>

						<ul use:autoAnimate={{ duration: 100 }}>
							{#each columns as column, index}
								<li
									on:dragover={(e) => {
										e.preventDefault();
										hoveredColumnIndex = index;
									}}
									style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 50px 40px;"
									class="grid gap-2 mt-3 {draggingColumn?.drag_id == column.drag_id
										? 'opacity-0'
										: ''}"
								>
									<button
										on:dragstart={(e) => {
											//@ts-ignore
											let rect = e.target.getBoundingClientRect();
											dragMouseCoords = {
												x: e.clientX,
												y: e.clientY,
												startX: e.clientX - rect.left,
												startY: e.clientY - rect.top,
												//@ts-ignore
												width: e.target.parentElement.offsetWidth
											};
											draggingColumn = column;
											draggingColumnIndex = index;
										}}
										on:drag={(e) => {
											if (e.clientX === 0 && e.clientY === 0) return;
											//@ts-ignore
											dragMouseCoords = { ...dragMouseCoords, x: e.clientX, y: e.clientY };
										}}
										on:dragend={() => {
											draggingColumn = null;
											draggingColumnIndex = null;
											dragMouseCoords = null;
											hoveredColumnIndex = null;
										}}
										draggable={true}
										class="flex items-center justify-center cursor-grab"
									>
										<HamburgerIcon class="h-5" />
									</button>

									<div class="flex flex-col gap-2 py-1 w-full text-center">
										<input
											type="text"
											bind:value={column.id}
											class="px-3 py-2 w-full text-sm bg-white data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#2A2A2A] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
										/>
									</div>

									<div class="flex flex-col gap-2 py-1 w-full text-center">
										<Select.Root>
											<Select.Trigger asChild let:builder>
												<Button
													builders={[builder]}
													variant="outline"
													class="flex items-center justify-between gap-8 pl-3 pr-2 h-[38px] min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
												>
													<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
														{column.dtype ? column.dtype : 'Select Data Type'}
													</span>

													<ChevronDown class="h-4 w-4" />
												</Button>
											</Select.Trigger>
											<Select.Content side="left" class="max-h-64 overflow-y-auto">
												{#each actionTableDTypes as dType}
													<Select.Item
														on:click={() => (column.dtype = dType)}
														value={dType}
														label={dType}
														class="flex justify-between gap-10 cursor-pointer"
													>
														{dType}
													</Select.Item>
												{/each}
											</Select.Content>
										</Select.Root>
									</div>

									<div class="flex items-center justify-center">
										<Checkbox
											on:checkedChange={(e) => {
												if (e.detail.value) {
													column.gen_config = {
														model: '',
														messages: [
															{
																role: 'system',
																content: ''
															},
															{
																role: 'user',
																content: ''
															}
														],
														temperature: 1,
														max_tokens: 1000,
														top_p: 0.1
													};
												} else {
													column.gen_config = null;
												}
											}}
											checked={!!column.gen_config}
											class="h-5 w-5"
										/>
									</div>

									<Button
										variant="ghost"
										on:click={() => (columns = columns.filter((_, idx) => index !== idx))}
										class="p-0 h-8 w-8 aspect-square rounded-full place-self-center"
									>
										<CloseIcon class="h-5" />
									</Button>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</div>

			<div class="mt-3 px-8 pb-4">
				<button
					on:click={() =>
						(columns = [
							...columns,
							{ id: '', dtype: 'str', drag_id: uuidv4(), index: false, gen_config: null }
						])}
					class="flex items-center justify-center gap-2 h-10 w-full text-sm text-[#4169e1] data-dark:text-[#5b7ee5] hover:text-[#12359e] data-dark:hover:text-[#425eae] border border-dashed border-[#4169e1] data-dark:border-[#5b7ee5] hover:border-[#12359e] data-dark:hover:border-[#425eae] rounded-lg transition-colors"
				>
					<AddIcon class="h-4 w-4" />
					Add column
				</button>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isAddingTable = false)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					on:click={handleAddTable}
					class="relative grow px-6 rounded-full"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<!-- Dragged item -->
{#if dragMouseCoords && draggingColumn}
	<li
		style="grid-template-columns: 30px repeat(2, minmax(0, 1fr)) 40px; top: {dragMouseCoords.y -
			dragMouseCoords.startY -
			15}px; left: {dragMouseCoords.x -
			dragMouseCoords.startX -
			15}px; width: {dragMouseCoords.width}px;"
		class="absolute z-[9999] grid gap-2 mt-3 bg-[#F4F5FA] data-dark:bg-[#42464e] pointer-events-none"
	>
		<button class="flex items-center justify-center cursor-grab">
			<HamburgerIcon class="h-5" />
		</button>

		<div class="flex flex-col gap-2 py-1 w-full text-center">
			<input
				type="text"
				bind:value={draggingColumn.id}
				class="px-3 py-2 w-full text-sm bg-white data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#2A2A2A] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
			/>
		</div>

		<div class="flex flex-col gap-2 py-1 w-full text-center">
			<Select.Root>
				<Select.Trigger asChild let:builder>
					<Button
						builders={[builder]}
						variant="outline"
						class="flex items-center justify-between gap-8 pl-3 pr-2 h-[38px] min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
					>
						<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
							{draggingColumn.dtype ? draggingColumn.dtype : 'Select Data Type'}
						</span>

						<ChevronDown class="h-4 w-4" />
					</Button>
				</Select.Trigger>
				<Select.Content side="bottom" class="max-h-96 overflow-y-auto">
					{#each actionTableDTypes as dType}
						<Select.Item
							value={dType}
							label={dType}
							class="flex justify-between gap-10 cursor-pointer"
						>
							{dType}
						</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
		</div>

		<Button variant="ghost" class="p-0 h-8 w-8 aspect-square rounded-full place-self-center">
			<CloseIcon class="h-5" />
		</Button>
	</li>
{/if}
