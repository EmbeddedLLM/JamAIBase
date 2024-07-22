<script lang="ts">
	import Papa from 'papaparse';
	import autoAnimate from '@formkit/auto-animate';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import type { GenTable } from '$lib/types';

	import { toast } from 'svelte-sonner';
	import Portal from '$lib/components/Portal.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';

	export let tableData: GenTable | undefined;
	$: filterTableCols = (tableData?.cols ?? []).filter(
		({ id }) => id !== 'ID' && id !== 'Updated at'
	);
	export let isMatchingImportCols: {
		filename: string;
		rows: Record<string, string>[];
		cols: { id: string; name: string }[];
	} | null;
	export let uploadImportFile: (file: File) => Promise<void>;

	let isLoadingImport = false;
	let match: { id: string; name: string }[] = [];
	let include: string[] = [];
	$: if (!!isMatchingImportCols) {
		match = isMatchingImportCols.cols;
		include = isMatchingImportCols.cols.map((i) => i.id);
	}

	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = null;
	let draggingColumn: NonNullable<typeof isMatchingImportCols>['cols'][number] | null = null;
	let draggingColumnIndex: number | null = null;
	let hoveredColumnIndex: number | null = null;

	$: if (
		draggingColumnIndex != null &&
		hoveredColumnIndex != null &&
		draggingColumnIndex != hoveredColumnIndex
	) {
		[match[draggingColumnIndex], match[hoveredColumnIndex]] = [
			match[hoveredColumnIndex],
			match[draggingColumnIndex]
		];

		draggingColumnIndex = hoveredColumnIndex;
	}

	function handleDragOver(e: DragEvent, index: number) {
		if (draggingColumnIndex !== null) {
			const rect = (e.target as HTMLDivElement).getBoundingClientRect();
			const y = e.clientY - rect.top;
			if ((draggingColumnIndex < index && y > 22) || (draggingColumnIndex > index && y < 22)) {
				hoveredColumnIndex = index;
			}
		}
	}

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
			return toast.error('No columns selected.');
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
	open={!!isMatchingImportCols}
	onOpenChange={(e) => {
		if (!e) {
			isMatchingImportCols = null;
			match = [];
		}
	}}
>
	<Dialog.Content class="max-h-[90vh] min-w-[45rem]">
		<Dialog.Header>Drag columns to match</Dialog.Header>

		<div class="grow w-full overflow-auto">
			<div class="grid grid-cols-[minmax(0,_350px)_30px_minmax(0,_350px)] px-6 py-3 h-full w-full">
				<div use:autoAnimate={{ duration: 100 }} class="flex flex-col gap-2">
					<span class="ml-2 font-medium">Source file</span>
					{#each match as col, index (col.id)}
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						<div
							title={col.name}
							on:click|stopPropagation
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
								draggingColumn = col;
								draggingColumnIndex = index;
							}}
							on:drag={(e) => {
								if (e.clientX === 0 && e.clientY === 0) return;
								//@ts-ignore
								dragMouseCoords = { ...dragMouseCoords, x: e.clientX, y: e.clientY };
							}}
							on:dragover|preventDefault={(e) => handleDragOver(e, index)}
							on:dragend={() => {
								dragMouseCoords = null;
								draggingColumn = null;
								draggingColumnIndex = null;
								hoveredColumnIndex = null;
							}}
							draggable={!!col.name}
							class="flex items-center gap-2 px-2 h-[40px] bg-white data-dark:bg-[#42464E] {col.name
								? 'border cursor-grab hover:shadow-float'
								: ''} border-[#E4E7EC] data-dark:border-[#333] {draggingColumn?.id === col.id
								? 'opacity-0'
								: include.includes(col.id) && index + 1 <= filterTableCols.length
									? draggingColumnIndex === null && col.name
										? 'hover:shadow-float'
										: ''
									: 'opacity-60'} transition-shadow rounded-sm"
						>
							<button class="{!col.name ? 'opacity-0' : ''} pointer-events-none">
								<GripVertical size={18} />
							</button>

							<span
								class="font-medium text-sm text-[#666] data-dark:text-white line-clamp-1 break-all"
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
									? 'opacity-0 pointer-events-none'
									: ''}"
							/>
						</div>
					{/each}
				</div>

				<div class="flex flex-col gap-2">
					<span>&nbsp;</span>
					{#each match as col, index}
						<div
							class="flex items-center justify-center h-[40px] {col.name &&
							include.includes(col.id) &&
							index + 1 <= filterTableCols.length
								? ''
								: 'opacity-0'}"
						>
							<ArrowRightIcon class="h-4" />
						</div>
					{/each}
				</div>

				<div class="flex flex-col gap-2">
					<span class="ml-2 font-medium">Table</span>
					{#each filterTableCols as col}
						{@const colType = !col.gen_config ? 'input' : 'output'}
						<div
							title={col.id}
							class="flex items-center gap-2 px-2 h-[40px] bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] rounded-sm"
						>
							<span
								style="background-color: {colType === 'input'
									? '#E9EDFA'
									: '#FFEAD5'}; color: {colType === 'input' ? '#6686E7' : '#FD853A'};"
								class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
							>
								<span class="capitalize text-xs font-medium px-1">
									{colType}
								</span>
								<span
									class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
								>
									{col.dtype}
								</span>
							</span>

							<span
								class="font-medium text-sm text-[#666] data-dark:text-white line-clamp-1 break-all"
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
				class="hidden relative grow px-6 rounded-full"
			/>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleUploadMatched}
					type="button"
					loading={isLoadingImport}
					disabled={isLoadingImport}
					class="relative grow px-6 rounded-full"
				>
					Import
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

{#if dragMouseCoords && draggingColumn}
	<Portal>
		<div
			style="top: {dragMouseCoords.y - dragMouseCoords.startY}px; left: {dragMouseCoords.x -
				dragMouseCoords.startX}px; width: {dragMouseCoords.width}px;"
			class="absolute z-[9999] flex items-center gap-2 px-2 h-[40px] bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] pointer-events-none"
		>
			<button>
				<GripVertical size={18} />
			</button>

			<span class="font-medium text-sm text-[#666] data-dark:text-white line-clamp-1 break-all">
				{draggingColumn.name}
			</span>
		</div>
	</Portal>
{/if}
