<script lang="ts">
	import * as Select from '$lib/components/ui/select';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { Button } from '$lib/components/ui/button';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import type { GenTable } from '$lib/types';
	import ArrowDownIcon from '$lib/icons/ArrowDownIcon.svelte';
	import { ChevronDown } from '@lucide/svelte';

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
	}

	let { tableType, tableData }: Props = $props();
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="action"
				title="Table actions"
				class="text aspect-square h-8 w-auto gap-1 bg-[#E9EDFA] p-0 px-2 text-[#4169E1] sm:h-9"
			>
				<svg
					viewBox="0 0 6 8"
					fill="none"
					xmlns="http://www.w3.org/2000/svg"
					class:rotate-180={page.url.searchParams.get('asc') === '1'}
					class="h-2.5 w-2.5"
				>
					<path
						d="M2.92188 0.5V7.5"
						stroke="#4169E1"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
					<path
						d="M5.34615 5.07692L2.92308 7.5L0.5 5.07692"
						stroke="#4169E1"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>

				{page.url.searchParams.get('sort_by') ?? 'ID'}

				<ChevronDown class="ml-1 size-4 flex-[0_0_auto]" />
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>

	<DropdownMenu.Content data-testid="table-sorter" class="max-w-[20rem] p-2 text-[#344054]">
		<DropdownMenu.Group class="flex flex-col gap-2 py-1 text-sm">
			<div class="flex gap-1">
				<div class="flex w-full flex-col text-center">
					<Select.Root
						type="single"
						value={page.url.searchParams.get('sort_by') ?? 'ID'}
						onValueChange={(v) => {
							if (v === 'ID') {
								page.url.searchParams.delete('sort_by');
							} else {
								page.url.searchParams.set('sort_by', v);
							}
							goto(`?${page.url.searchParams}`, {
								replaceState: true,
								invalidate: [`${tableType}-table:slug`]
							});
						}}
					>
						<Select.Trigger
							class="flex h-[32px] min-w-full max-w-32 items-center justify-between !gap-2 border border-[#E4E7EC] bg-white pl-3 pr-2 data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] sm:gap-8"
						>
							{#snippet children()}
								<span class="line-clamp-1 break-words text-left font-normal">
									{page.url.searchParams.get('sort_by') ?? 'ID'}
								</span>
							{/snippet}
						</Select.Trigger>
						<Select.Content class="max-h-64 max-w-64 overflow-y-auto">
							{#each tableData?.cols ?? [] as column}
								{@const colType = !column.gen_config ? 'input' : 'output'}
								<Select.Item
									value={column.id}
									label={column.id}
									class="flex cursor-pointer gap-1 break-all"
								>
									{#if !['ID', 'Updated at'].includes(column.id)}
										<span
											style="background-color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
											class:pr-1={column.gen_config?.object !== 'gen_config.llm' ||
												!column.gen_config.multi_turn}
											class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-lg px-0.5 py-1 text-xxs text-white sm:text-xs"
										>
											<span class="px-1 font-medium capitalize">
												{colType}
											</span>
											<span
												style="color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
												class="w-min select-none whitespace-nowrap rounded-md bg-white px-1 font-medium"
											>
												{column.dtype}
											</span>

											<!-- {#if column.gen_config?.object === 'gen_config.llm' && column.gen_config.multi_turn}
											<hr class="ml-1 h-3 border-l border-white" />
											<div class="relative h-4 w-[18px]">
												<MultiturnChatIcon class="absolute h-[18px] -translate-y-px text-white" />
											</div>
										{/if} -->
										</span>
									{/if}

									{column.id}
								</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>

				<div class="flex w-full flex-col text-center">
					<Select.Root
						type="single"
						value={page.url.searchParams.get('asc') ?? '0'}
						onValueChange={(v) => {
							if (v === '0') {
								page.url.searchParams.delete('asc');
							} else {
								page.url.searchParams.set('asc', '1');
							}
							goto(`?${page.url.searchParams}`, {
								replaceState: true,
								invalidate: [`${tableType}-table:slug`]
							});
						}}
					>
						<Select.Trigger
							class="flex h-[32px] min-w-full items-center justify-between !gap-2 border border-[#E4E7EC] bg-white pl-3 pr-2 data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] sm:gap-8"
						>
							{#snippet children()}
								<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
									{page.url.searchParams.get('asc') === '1' ? 'Ascending' : 'Descending'}
								</span>
							{/snippet}
						</Select.Trigger>
						<Select.Content class="max-h-64 overflow-y-auto">
							{#each ['0', '1'] as sortDirection}
								<Select.Item
									value={sortDirection}
									label={sortDirection === '1' ? 'Ascending' : 'Descending'}
									class="flex cursor-pointer justify-between gap-10"
								>
									{sortDirection === '1' ? 'Ascending' : 'Descending'}
								</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
			</div>

			<!-- <span class="ml-1 text-[#98A2B3]">
				Order by
				<span class="font-medium text-[#667085]">Created</span>
			</span>

			<div
				style="grid-template-columns: repeat(2, minmax(5rem, 1fr));"
				class="relative grid w-full place-items-center rounded-full bg-[#E4E7EC] p-0.5 after:pointer-events-none after:absolute after:left-0.5 after:top-1/2 after:z-0 after:h-[calc(100%_-_4px)] after:w-1/2 after:-translate-y-1/2 after:rounded-full after:bg-white after:transition-transform after:duration-200 after:content-[''] data-dark:bg-gray-700 {page.url.searchParams.get(
					'asc'
				) === '1'
					? 'after:translate-x-0'
					: 'after:translate-x-[calc(100%_-_4px)]'}"
			>
				<DropdownMenuPrimitive.Item
					onclick={() => {
						const query = new URLSearchParams(page.url.searchParams.toString());
						query.set('asc', '1');
						goto(`?${query.toString()}`, { replaceState: true });
					}}
					class="z-10 w-full rounded-full px-4 py-1 text-center transition-colors ease-in-out {page.url.searchParams.get(
						'asc'
					) === '1'
						? 'text-[#667085]'
						: 'text-[#98A2B3]'} cursor-pointer"
				>
					Ascending
				</DropdownMenuPrimitive.Item>

				<DropdownMenuPrimitive.Item
					onclick={() => {
						const query = new URLSearchParams(page.url.searchParams.toString());
						query.delete('asc');
						goto(`?${query.toString()}`, { replaceState: true });
					}}
					class="z-10 w-full rounded-full px-4 py-1 text-center transition-colors ease-in-out {page.url.searchParams.get(
						'asc'
					) !== '1'
						? 'text-[#667085]'
						: 'text-[#98A2B3]'} cursor-pointer"
				>
					Descending
				</DropdownMenuPrimitive.Item>
			</div> -->
		</DropdownMenu.Group>
	</DropdownMenu.Content>
</DropdownMenu.Root>
