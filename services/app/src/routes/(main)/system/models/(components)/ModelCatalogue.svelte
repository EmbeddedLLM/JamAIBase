<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import Fuse from 'fuse.js';
	import { ChevronLeft, ChevronRight, Plus, Search, SortAsc, SortDesc } from '@lucide/svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { modelConfigSort } from '$globalStore';
	import { MODEL_TYPES } from '$lib/constants';
	import type { ModelConfig } from '$lib/types';
	import type { PageData } from '../$types';

	import Input from '$lib/components/ui/input/input.svelte';
	import * as Pagination from '$lib/components/ui/pagination';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import AddDeploymentDialog from './AddDeploymentDialog.svelte';
	import DeleteModelConfigDialog from './DeleteModelConfigDialog.svelte';
	import ModelConfigCard from './ModelConfigCard.svelte';

	let containerWidth = $state(0);
	let columnsCount = $derived.by(() => {
		if (containerWidth < 768) return 1;
		else if (containerWidth < 1024) return 2;
		else if (containerWidth < 1200) return 3;
		else if (containerWidth < 1600) return 4;
		else return 5;
	});
	let itemsPerPage = $derived(columnsCount * 3 - 1);

	let {
		data,
		isAddingModelConfig = $bindable()
	}: { data: PageData; isAddingModelConfig: boolean } = $props();

	let searchQuery = $state('');
	let pageQParam = $derived(parseInt(page.url.searchParams.get('page') ?? ''));
	let currentPage = $derived(isNaN(pageQParam) || pageQParam < 1 ? 1 : pageQParam);

	let editOpen = $state<{ open: boolean; value: ModelConfig | null }>({
		open: false,
		value: null
	});
	let deleteOpen = $state<{ open: boolean; value: ModelConfig | null }>({
		open: false,
		value: null
	});
	let deployOpen = $state<{ open: boolean; value: ModelConfig | null }>({
		open: false,
		value: null
	});

	function filterModelConfigs(modelConfigs: ModelConfig[], query: string, filter: string) {
		let filtered =
			filter === 'all'
				? modelConfigs
				: modelConfigs.filter((modelConfig) => modelConfig.type === filter);

		const fuse = new Fuse(modelConfigs, {
			keys: ['name', 'id'],
			threshold: 0.4, // 0.0 = exact match, 1.0 = match all
			includeScore: false
		});

		if (query) {
			filtered = fuse.search(query).map((result) => result.item);
		}

		filtered = [...filtered].sort((a, b) => {
			if ($modelConfigSort.orderBy === 'created_at') {
				const dateA = new Date(a.created_at).getTime();
				const dateB = new Date(b.created_at).getTime();
				return $modelConfigSort.order === 'asc' ? dateA - dateB : dateB - dateA;
			}

			return 0;
		});

		return filtered;
	}

	function getPaginatedModelConfigs(
		modelConfigs: ModelConfig[],
		query: string,
		filter: string,
		page: number,
		perPage: number
	) {
		const filteredConfigs = filterModelConfigs(modelConfigs, query, filter);

		const totalPages = Math.max(1, Math.ceil(filteredConfigs.length / perPage));
		const safeCurrentPage = Math.min(currentPage, totalPages);

		const startIndex = (safeCurrentPage - 1) * perPage;
		const paginatedConfigs = filteredConfigs.slice(startIndex, startIndex + perPage);

		return {
			filteredConfigs,
			paginatedConfigs
		};
	}

	function handlePageChange(newPage: number) {
		currentPage = newPage;
		page.url.searchParams.set('page', newPage.toString());
		goto(`?${page.url.searchParams}`, { replaceState: true });
	}

	function toggleSort() {
		$modelConfigSort.order = $modelConfigSort.order === 'asc' ? 'desc' : 'asc';

		currentPage = 1;
	}
</script>

<section
	bind:clientWidth={containerWidth}
	class="flex w-full flex-col items-start space-y-4 @container"
>
	<h2 class="">Model Catalogue</h2>
	<div class="flex items-center gap-2">
		<div class="relative">
			<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
				<Search size={18} class="text-gray-400" />
			</div>
			<Input
				type="text"
				oninput={() => (currentPage = 1)}
				bind:value={searchQuery}
				placeholder="Search models"
				class="w-64 rounded-lg border border-gray-300 bg-gray-200/40 py-2 pl-10 pr-4"
			/>
		</div>
		<button
			onclick={() => toggleSort()}
			class="flex h-10 items-center gap-1 rounded-lg border border-gray-300 bg-gray-200/40 px-3 py-2 text-sm transition-colors hover:bg-gray-200"
		>
			{#if $modelConfigSort.order === 'asc'}
				<SortAsc size={16} />
			{:else}
				<SortDesc size={16} />
			{/if}
			Date created
		</button>
	</div>

	<div class="flex w-full items-center justify-between">
		<div class="flex gap-2 text-sm">
			{#each ['all', ...Object.keys(MODEL_TYPES)] as modelType}
				<button
					onclick={() => {
						$modelConfigSort.filter = modelType;
						currentPage = 1;
					}}
					class="z-50 border {$modelConfigSort.filter === modelType
						? 'border-[#ABEE58] bg-[#F4FFD9] text-[#1D2939]'
						: 'border-transparent text-[#98A2B3]'} rounded-3xl px-3 py-1 capitalize transition-colors"
				>
					{MODEL_TYPES[modelType] ?? 'All models'}
				</button>
			{/each}
		</div>

		{#await data.modelConfigs then modelConfigs}
			{#if modelConfigs.data}
				{@const filteredConfigs = filterModelConfigs(
					modelConfigs.data,
					searchQuery,
					$modelConfigSort.filter
				)}
				<Pagination.Root
					page={currentPage}
					count={filteredConfigs.length}
					perPage={itemsPerPage}
					siblingCount={1}
					class="z-50 mx-0 w-[unset]"
				>
					{#snippet children({ pages, currentPage })}
						<Pagination.Content>
							<Pagination.Item>
								<Pagination.PrevButton>
									{#snippet child({ props })}
										<button
											{...props}
											onclick={() => {
												if (currentPage > 1) {
													handlePageChange(currentPage - 1);
												}
											}}
											class="mt-0.5 inline-flex h-6 w-6 items-center justify-center whitespace-nowrap rounded-full text-sm font-medium ring-offset-background transition-colors hover:bg-[#F2F4F7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
										>
											<ChevronLeft class="h-4 w-4" />
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
													onclick={() => {
														handlePageChange(page.value);
													}}
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
											onclick={() => {
												if (currentPage < Math.ceil(filteredConfigs.length / itemsPerPage)) {
													handlePageChange(currentPage + 1);
												}
											}}
											class="mt-0.5 inline-flex h-6 w-6 items-center justify-center whitespace-nowrap rounded-full text-sm font-medium ring-offset-background transition-colors hover:bg-[#F2F4F7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
										>
											<ChevronRight class="h-4 w-4" />
										</button>
									{/snippet}
								</Pagination.NextButton>
							</Pagination.Item>
						</Pagination.Content>
					{/snippet}
				</Pagination.Root>
			{/if}
		{/await}
	</div>

	<div
		style="grid-auto-rows: 230px;"
		class="model-configs mt-3 grid w-full gap-4 [scrollbar-gutter:stable]"
	>
		{#await data.modelConfigs}
			{#each Array(6) as _}
				<Skeleton class="h-full w-full rounded-xl bg-gray-300" />
			{/each}
		{:then modelConfigs}
			{#if modelConfigs.data}
				{@const { filteredConfigs, paginatedConfigs } = getPaginatedModelConfigs(
					modelConfigs.data,
					searchQuery,
					$modelConfigSort.filter,
					currentPage,
					itemsPerPage
				)}
				<button
					onclick={() => (isAddingModelConfig = true)}
					class="flex items-center justify-center gap-x-2 space-y-2 rounded-xl bg-gray-200 p-4 text-gray-700 transition-colors hover:bg-gray-300"
				>
					<Plus size={20} /> Add model
				</button>
				{#if filteredConfigs.length === 0}
					<div class="flex items-center justify-center pb-4">
						<p class="text-center text-sm text-gray-500">
							{$modelConfigSort.filter === 'all'
								? 'No model config found.'
								: `No ${MODEL_TYPES[$modelConfigSort.filter] ?? $modelConfigSort.filter} models found in the catalogue.`}
						</p>
					</div>
				{:else}
					{#each paginatedConfigs as modelConfig}
						<ModelConfigCard
							{modelConfig}
							{currentPage}
							bind:editOpen
							bind:deleteOpen
							bind:deployOpen
						/>
					{/each}
				{/if}
			{:else}
				<div class="lg col-span-full flex items-center justify-center pb-4">
					<p class="text-center text-sm text-gray-500">
						{modelConfigs?.error.message || JSON.stringify(modelConfigs?.error)}
					</p>
				</div>
			{/if}
		{/await}
	</div>
</section>

<DeleteModelConfigDialog bind:open={deleteOpen} />
<AddDeploymentDialog bind:open={deployOpen} />

<style>
	.model-configs {
		grid-template-columns: repeat(1, minmax(0, 1fr));
	}

	@container (min-width: 768px) {
		.model-configs {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@container (min-width: 1024px) {
		.model-configs {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	@container (min-width: 1200px) {
		.model-configs {
			grid-template-columns: repeat(4, 1fr);
		}
	}

	@container (min-width: 1600px) {
		.model-configs {
			grid-template-columns: repeat(5, 1fr);
		}
	}
</style>
