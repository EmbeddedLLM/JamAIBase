<script lang="ts">
	import Papa from 'papaparse';
	import autoAnimate from '@formkit/auto-animate';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import type { GenTable } from '$lib/types';

	import { toast } from 'svelte-sonner';
	import Portal from '$lib/components/Portal.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import DraggableList from '$lib/components/DraggableList.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';

	interface Props {
		tableData: GenTable | undefined;
		isMatchingImportCols: {
			filename: string;
			rows: Record<string, string>[];
			cols: { id: string; name: string }[];
		} | null;
		uploadImportFile: (file: File) => Promise<void>;
	}

	let { tableData, isMatchingImportCols = $bindable(), uploadImportFile }: Props = $props();

	let filterTableCols = $derived(
		(tableData?.cols ?? []).filter(({ id }) => id !== 'ID' && id !== 'Updated at')
	);
	let isLoadingImport = $state(false);
	let match: { id: string; name: string }[] = $state([]);
	let include: string[] = $state([]);
	$effect(() => {
		if (!!isMatchingImportCols) {
			match = isMatchingImportCols.cols;
			include = isMatchingImportCols.cols.map((i) => i.id);
		}
	});

	function handleUploadMatched() {
		if (!tableData || !isMatchingImportCols) return;

		isLoadingImport = true;

		const filterTableCols = tableData.cols.filter(({ id }) => id !== 'ID' && id !== 'Updated at');
		let sourceToTableMap: Record<string, string> = {};
		match.forEach((col, index) => {
			if (col.name && filterTableCols[index] && include.includes(col.id)) {
				sourceToTableMap[col.name] = filterTableCols[index].id;
			}
		});

		if (Object.keys(sourceToTableMap).length === 0) {
			isLoadingImport = false;
			return toast.error('No columns selected.', { id: 'no-columns-selected' });
		}

		let renameSourceCols = [];
		for (let i = 0; i < isMatchingImportCols.rows.length; ++i) {
			let obj: Record<string, string> = {};
			isMatchingImportCols.cols.forEach((key) => {
				const targetCol = sourceToTableMap[key.name];
				if (targetCol) {
					// filter out cells with missing values
					if (!isMatchingImportCols?.rows[i][key.name]) return;
					obj[targetCol] = isMatchingImportCols?.rows[i][key.name] ?? '';
				}
			});
			renameSourceCols[i] = obj;
		}

		const parsed = Papa.unparse(renameSourceCols);

		const file = new File([new Blob([parsed])], isMatchingImportCols.filename);

		uploadImportFile(file).then(() => {
			isMatchingImportCols = null;
			isLoadingImport = false;
		});
	}
</script>

<Dialog.Root
	bind:open={() => !!isMatchingImportCols, () => (isMatchingImportCols = null)}
	onOpenChange={(e) => {
		if (!e) {
			match = [];
		}
	}}
>
	<Dialog.Content data-testid="column-match-dialog" class="max-h-[90vh] w-[clamp(0px,45rem,100%)]">
		<Dialog.Header class="[&>hr]:border-0">Drag columns to match</Dialog.Header>

		<div class="w-full grow overflow-auto px-3">
			<div
				class="grid h-full w-full grid-cols-[minmax(0,_350px)_30px_minmax(0,_350px)] rounded-lg border border-[#F2F4F7] bg-[#F2F4F7] px-3 py-3"
			>
				<DraggableList tagName="ul" bind:itemList={match} class="flex flex-col gap-2">
					{#snippet leading()}
						<span class="text-sm text-[#1D2939] sm:text-base">Source file</span>
					{/snippet}

					{#snippet listItem({
						item: col,
						itemIndex: index,
						dragStart,
						dragMove,
						dragOver,
						dragEnd,
						draggingItem: draggingColumn,
						draggingItemIndex: draggingColumnIndex
					})}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<!-- svelte-ignore a11y_click_events_have_key_events -->
						<div
							title={col.name}
							onclick={(e) => e.stopPropagation()}
							ondragstart={(e) => dragStart(e, col, index, !!col.name)}
							ondrag={dragMove}
							ondragover={(e) => {
								e.preventDefault();
								dragOver(e, index);
							}}
							ondragend={dragEnd}
							ontouchstart={(e) => dragStart(e, col, index, !!col.name)}
							ontouchmove={dragMove}
							ontouchend={dragEnd}
							draggable={!!col.name}
							class="flex h-[40px] items-center gap-2 bg-white px-2 data-dark:bg-[#42464E] {col.name
								? 'cursor-grab border hover:shadow-float'
								: ''} border-[#E4E7EC] data-dark:border-[#333] {draggingColumn?.id === col.id
								? 'opacity-0'
								: include.includes(col.id) && index + 1 <= filterTableCols.length
									? draggingColumnIndex === null && col.name
										? 'hover:shadow-float'
										: ''
									: 'opacity-60'} touch-none rounded transition-shadow"
						>
							<button
								title="Drag to reorder columns"
								class="{!col.name ? 'opacity-0' : ''} pointer-events-none"
							>
								<GripVertical size={18} />
							</button>

							<span
								class="pointer-events-none line-clamp-1 break-all text-xs font-medium text-[#666] data-dark:text-white sm:text-sm"
							>
								{col.name}
							</span>

							<Checkbox
								on:checkedChange={() =>
									(include = include.includes(col.id)
										? include.filter((i) => i !== col.id)
										: [...include, col.id])}
								checked={include.includes(col.id) && index + 1 <= filterTableCols.length}
								class="ml-auto mt-[1px] h-[18px] w-[18px] [&>svg]:h-3.5 [&>svg]:w-3.5 [&>svg]:translate-x-[1px] {!col.name ||
								index + 1 > filterTableCols.length
									? 'pointer-events-none opacity-0'
									: ''}"
							/>
						</div>
					{/snippet}

					{#snippet draggedItem({ dragMouseCoords, draggingItem: draggingColumn })}
						<Portal>
							{#if dragMouseCoords && draggingColumn}
								<div
									inert
									style="top: {dragMouseCoords.y -
										dragMouseCoords.startY}px; left: {dragMouseCoords.x -
										dragMouseCoords.startX}px; width: {dragMouseCoords.width}px;"
									class="pointer-events-none fixed z-[9999] flex h-[40px] items-center gap-2 rounded border border-[#E4E7EC] bg-white px-2 data-dark:border-[#333] data-dark:bg-[#42464E]"
								>
									<button>
										<GripVertical size={18} />
									</button>

									<span
										class="line-clamp-1 break-all text-xs font-medium text-[#666] data-dark:text-white sm:text-sm"
									>
										{draggingColumn.name}
									</span>
								</div>
							{/if}
						</Portal>
					{/snippet}
				</DraggableList>

				<div class="flex flex-col gap-2">
					<span class="text-sm sm:text-base">&nbsp;</span>
					{#each match as col, index}
						<div
							class="flex h-[40px] items-center justify-center {col.name &&
							include.includes(col.id) &&
							index + 1 <= filterTableCols.length
								? ''
								: 'opacity-0'}"
						>
							<ArrowRightIcon class="h-4 text-[#475467]" />
						</div>
					{/each}
				</div>

				<div class="flex flex-col gap-2">
					<span class="text-sm text-[#1D2939] sm:text-base">Table</span>
					{#each filterTableCols as col}
						{@const colType = !col.gen_config ? 'input' : 'output'}
						<div
							title={col.id}
							class="flex h-[40px] items-center gap-2 rounded-sm border border-[#E4E7EC] bg-white px-2 data-dark:border-[#333] data-dark:bg-[#42464E]"
						>
							<span
								style="background-color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
								class:pr-1={col.gen_config?.object !== 'gen_config.llm' ||
									!col.gen_config.multi_turn}
								class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-lg px-0.5 py-1 text-xxs text-white sm:text-xs"
							>
								<span class="px-1 font-medium capitalize">
									{colType}
								</span>
								<span
									style="color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
									class="w-min select-none whitespace-nowrap rounded-md bg-white px-1 font-medium"
								>
									{col.dtype}
								</span>
							</span>

							<span
								class="line-clamp-1 break-all text-xs font-medium text-[#666] data-dark:text-white sm:text-sm"
							>
								{col.id}
							</span>
						</div>
					{/each}
				</div>
			</div>

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoadingImport}
				disabled={isLoadingImport}
				class="relative hidden grow px-6"
			/>
		</div>

		<Dialog.Actions class="border-0">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					onclick={handleUploadMatched}
					type="button"
					loading={isLoadingImport}
					disabled={isLoadingImport}
					class="relative grow px-6"
				>
					Import
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
