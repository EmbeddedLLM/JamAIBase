<script lang="ts">
	import { page } from '$app/stores';
	import * as constants from '$lib/constants';
	import type { GenTable, GenTableCol, GenTableRow } from '$lib/types';

	import * as Pagination from '$lib/components/ui/pagination';
	import ArrowLeftIcon from '$lib/icons/ArrowLeftIcon.svelte';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let table:
		| {
				error: number;
				message: {
					tableData: any;
					rows: any;
				};
				tableData?: undefined;
				rows?: undefined;
				total_rows?: undefined;
		  }
		| {
				tableData: GenTable;
				rows: GenTableRow[];
				total_rows: any;
				error?: undefined;
				message?: undefined;
		  }
		| undefined;
	export let selectedRows: string[];
	export let searchQuery: string;
	export let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean };

	$: count = table?.total_rows ?? 0;
	$: perPage = constants[`${tableType}RowsPerPage`];
	$: currentPage = parseInt($page.url.searchParams.get('page') ?? '1');
</script>

<div
	inert={isColumnSettingsOpen.showMenu}
	class="flex items-center justify-between px-4 py-3 min-h-[55px] border-t border-[#E4E7EC] data-dark:border-[#333]"
>
	<div class="flex items-end gap-6">
		<span class="text-sm font-medium text-[#666] data-dark:text-white">
			{#if !searchQuery}
				Showing {count == 0 ? 0 : perPage * currentPage - perPage + 1}-{perPage * currentPage >
				count
					? count
					: perPage * currentPage} of {count} rows
			{:else}
				Showing rows filtered by search query `{searchQuery}` (max 100 rows)
			{/if}
		</span>

		{#if selectedRows.length}
			<span class="text-xs font-medium text-[#666] data-dark:text-white">
				Selected {selectedRows.length} rows
			</span>
		{/if}
	</div>

	{#if count > 0 && !searchQuery}
		<Pagination.Root page={currentPage} {count} {perPage} let:pages class="w-[unset] mx-0">
			<Pagination.Content>
				<Pagination.Item>
					<Pagination.PrevButton asChild class="!mt-1 [all:unset] hover:[all:unset]">
						<a
							href="?page={currentPage - 1}"
							class="inline-flex items-center justify-center rounded-md text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
						>
							<ArrowLeftIcon class="h-4 w-4" />
						</a>
					</Pagination.PrevButton>
				</Pagination.Item>
				{#each pages as page (page.key)}
					{#if page.type === 'ellipsis'}
						<Pagination.Item>
							<Pagination.Ellipsis />
						</Pagination.Item>
					{:else}
						<Pagination.Item>
							<Pagination.Link asChild isActive={currentPage === page.value} {page}>
								<a
									href="?page={page.value}"
									class="inline-flex items-center justify-center rounded-md text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
								>
									{page.value}
								</a>
							</Pagination.Link>
						</Pagination.Item>
					{/if}
				{/each}
				<Pagination.Item>
					<Pagination.NextButton asChild class="!mt-1 [all:unset] hover:[all:unset]">
						<a
							href="?page={currentPage + 1}"
							class="inline-flex items-center justify-center rounded-md text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
						>
							<ArrowRightIcon class="h-4 w-4" />
						</a>
					</Pagination.NextButton>
				</Pagination.Item>
			</Pagination.Content>
		</Pagination.Root>
	{/if}
</div>
