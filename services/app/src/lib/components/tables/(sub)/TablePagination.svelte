<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import * as constants from '$lib/constants';
	import type { GenTable } from '$lib/types';

	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Pagination from '$lib/components/ui/pagination';
	import ArrowLeftIcon from '$lib/icons/ArrowLeftIcon.svelte';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
		tableRowsCount: number | undefined;
		searchQuery: string;
	}

	let { tableType, tableData = $bindable(), tableRowsCount, searchQuery }: Props = $props();

	let perPage = $derived(constants[`${tableType}RowsPerPage`]);
	let currentPage = $derived(parseInt(page.url.searchParams.get('page') ?? '1'));

	function pageNavigate(link: string) {
		if (!tableRowsState.loading) {
			tableRowsState.loading = true;
			goto(link);
		}
	}

	const modifySearchParam = (key: string, value: string) => {
		const query = new URLSearchParams(page.url.searchParams.toString());
		query.set(key, value);
		return `?${query.toString()}`;
	};
</script>

<div
	data-testid="table-pagination"
	data-sveltekit-preload-data={!tableData ? 'false' : 'hover'}
	inert={tableState.columnSettings.isOpen}
	class="flex max-h-[40px] min-h-[40px] items-center justify-between border-t border-[#E4E7EC] px-2 py-2 data-dark:border-[#333] sm:max-h-[55px] sm:min-h-[55px] sm:px-4 sm:py-3"
>
	{#if tableRowsCount !== undefined}
		<div class="flex flex-col sm:flex-row sm:items-end sm:gap-6">
			<span class="text-[clamp(0.4rem,2.75vw,0.875rem)] text-[#667085] data-dark:text-white">
				{#if !searchQuery}
					Showing {tableRowsCount === 0 ? 0 : perPage * currentPage - perPage + 1}-{perPage *
						currentPage >
					tableRowsCount
						? tableRowsCount
						: perPage * currentPage} of {tableRowsCount} rows
				{:else}
					Showing rows filtered by search query `{searchQuery}` (max 100 rows)
				{/if}
			</span>

			{#if tableState.selectedRows.length}
				<span
					class="text-[#667085] [font-size:_clamp(0.65rem,2.5vw,0.875rem)] data-dark:text-white"
				>
					Selected {tableState.selectedRows.length} rows
				</span>
			{/if}
		</div>

		{#key page.url.searchParams.get('asc')}
			{#if tableRowsCount > 0 && !searchQuery}
				<Pagination.Root page={currentPage} count={tableRowsCount} {perPage} class="mx-0 w-[unset]">
					{#snippet children({ pages })}
						<Pagination.Content>
							<Pagination.Item>
								<Pagination.PrevButton>
									{#snippet child({ props })}
										<button
											{...props}
											onclick={() =>
												pageNavigate(modifySearchParam('page', (currentPage - 1).toString()))}
											class="mt-0.5 inline-flex h-6 w-6 items-center justify-center whitespace-nowrap rounded-full text-sm font-medium ring-offset-background transition-colors hover:bg-[#F2F4F7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
										>
											<ArrowLeftIcon class="h-4 w-4" />
										</button>
									{/snippet}
								</Pagination.PrevButton>
							</Pagination.Item>
							{#each pages as page (page.key)}
								{#if page.type === 'ellipsis'}
									<Pagination.Item>
										<Pagination.Ellipsis />
									</Pagination.Item>
								{:else}
									{@const pageFontSize =
										99 % page.value === 99
											? 999 % page.value === 999
												? 'text-[0.6rem]'
												: 'text-xs'
											: 'text-sm'}
									<Pagination.Item>
										<Pagination.Link isActive={currentPage === page.value} {page}>
											{#snippet child({ props })}
												<button
													{...props}
													onclick={() =>
														pageNavigate(modifySearchParam('page', page.value.toString()))}
													style={currentPage === page.value
														? 'background: #E4E7EC; pointer-events: none;'
														: ''}
													class="inline-flex items-center justify-center {pageFontSize} h-6 w-6 whitespace-nowrap rounded-full font-medium text-[#475467] ring-offset-background transition-colors hover:bg-[#F2F4F7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
												>
													{page.value}
												</button>
											{/snippet}
										</Pagination.Link>
									</Pagination.Item>
								{/if}
							{/each}
							<Pagination.Item>
								<Pagination.NextButton>
									{#snippet child({ props })}
										<button
											{...props}
											onclick={() =>
												pageNavigate(modifySearchParam('page', (currentPage + 1).toString()))}
											class="mt-0.5 inline-flex h-6 w-6 items-center justify-center whitespace-nowrap rounded-full text-sm font-medium ring-offset-background transition-colors hover:bg-[#F2F4F7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
										>
											<ArrowRightIcon class="h-4 w-4" />
										</button>
									{/snippet}
								</Pagination.NextButton>
							</Pagination.Item>
						</Pagination.Content>
					{/snippet}
				</Pagination.Root>
			{/if}
		{/key}
	{:else}
		<Skeleton class="h-full w-20 sm:w-36" />
		<Skeleton class="h-full w-28 sm:w-52" />
	{/if}
</div>
