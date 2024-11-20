<script lang="ts">
	import { page } from '$app/stores';
	import { genTableRows } from '$lib/components/tables/tablesStore';
	import * as constants from '$lib/constants';
	import type { GenTable, GenTableCol, GenTableRow } from '$lib/types';

	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Pagination from '$lib/components/ui/pagination';
	import ArrowLeftIcon from '$lib/icons/ArrowLeftIcon.svelte';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable | undefined;
	export let tableRowsCount: number | undefined;
	export let selectedRows: string[];
	export let searchQuery: string;
	export let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean };

	$: perPage = constants[`${tableType}RowsPerPage`];
	$: currentPage = parseInt($page.url.searchParams.get('page') ?? '1');

	function paginationLinkNavigate(e: MouseEvent) {
		if ($genTableRows) {
			$genTableRows = undefined;
		} else {
			e.preventDefault();
		}
	}

	const modifySearchParam = (key: string, value: string) => {
		const query = new URLSearchParams($page.url.searchParams.toString());
		query.set(key, value);
		return `?${query.toString()}`;
	};
</script>

<div
	data-testid="table-pagination"
	data-sveltekit-preload-data={!tableData ? 'false' : 'hover'}
	inert={isColumnSettingsOpen.showMenu}
	class="flex items-center justify-between px-2 sm:px-4 py-2 sm:py-3 min-h-[40px] sm:min-h-[55px] max-h-[40px] sm:max-h-[55px] border-t border-[#E4E7EC] data-dark:border-[#333]"
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

			{#if selectedRows.length}
				<span
					class="[font-size:_clamp(0.65rem,2.5vw,0.875rem)] text-[#667085] data-dark:text-white"
				>
					Selected {selectedRows.length} rows
				</span>
			{/if}
		</div>

		{#key $page.url.searchParams.get('asc')}
			{#if tableRowsCount > 0 && !searchQuery}
				<Pagination.Root
					page={currentPage}
					count={tableRowsCount}
					{perPage}
					let:pages
					class="w-[unset] mx-0"
				>
					<Pagination.Content>
						<Pagination.Item>
							<Pagination.PrevButton asChild class="!mt-0.5 [all:unset] hover:[all:unset]">
								<a
									on:click={paginationLinkNavigate}
									href={modifySearchParam('page', (currentPage - 1).toString())}
									class="inline-flex items-center justify-center rounded-sm text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-6 w-6"
								>
									<ArrowLeftIcon class="h-4 w-4" />
								</a>
							</Pagination.PrevButton>
						</Pagination.Item>
						{#each pages as page (page.key)}
							{@const pageFontSize =
								99 % page.value === 99
									? 999 % page.value === 999
										? 'text-[0.6rem]'
										: 'text-xs'
									: 'text-sm'}
							{#if page.type === 'ellipsis'}
								<Pagination.Item>
									<Pagination.Ellipsis />
								</Pagination.Item>
							{:else}
								<Pagination.Item>
									<Pagination.Link asChild isActive={currentPage === page.value} {page}>
										<a
											on:click={paginationLinkNavigate}
											href={modifySearchParam('page', page.value.toString())}
											style={currentPage === page.value
												? 'background: #E4E7EC; pointer-events: none;'
												: ''}
											class="inline-flex items-center justify-center rounded-sm {pageFontSize} font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
										>
											{page.value}
										</a>
									</Pagination.Link>
								</Pagination.Item>
							{/if}
						{/each}
						<Pagination.Item>
							<Pagination.NextButton asChild class="!mt-0.5 [all:unset] hover:[all:unset]">
								<a
									on:click={paginationLinkNavigate}
									href={modifySearchParam('page', (currentPage + 1).toString())}
									class="inline-flex items-center justify-center rounded-sm text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-6 w-6"
								>
									<ArrowRightIcon class="h-4 w-4" />
								</a>
							</Pagination.NextButton>
						</Pagination.Item>
					</Pagination.Content>
				</Pagination.Root>
			{/if}
		{/key}
	{:else}
		<Skeleton class="h-full w-20 sm:w-36" />
		<Skeleton class="h-full w-28 sm:w-52" />
	{/if}
</div>
