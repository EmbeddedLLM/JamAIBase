<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import { AddTableDialog } from '../../../../routes/(main)/project/[project_id]/knowledge-table/(dialogs)';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Dialog from '$lib/components/ui/dialog';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import KnowledgeTableIcon from '$lib/icons/KnowledgeTableIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	interface Props {
		isSelectingKnowledgeTable: boolean;
		selectedKnowledgeTables: string; //TODO: Add type
	}

	let { isSelectingKnowledgeTable = $bindable(), selectedKnowledgeTables = $bindable() }: Props =
		$props();

	let searchQuery = $state('');
	let searchController: AbortController | null = null;
	let isLoadingSearch = $state(false);

	let pastKnowledgeTables: GenTable[] = $state([]);
	let isAddingTable = $state(false);

	let isLoadingKTables = $state(true);
	let isLoadingMoreKTables = $state(false);
	let moreKTablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	onMount(() => {
		getKnowledgeTables();

		return () => {
			pastKnowledgeTables = [];
		};
	});

	async function getKnowledgeTables() {
		if (!isLoadingKTables) {
			isLoadingMoreKTables = true;
		}

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/list?` +
				new URLSearchParams({
					offset: currentOffset.toString(),
					limit: limit.toString()
				}),
			{
				credentials: 'same-origin',
				headers: {
					'x-project-id': page.params.project_id ?? ''
				}
			}
		);
		currentOffset += limit;

		if (response.status == 200) {
			const moreKnowledgeTables = await response.json();
			if (moreKnowledgeTables.items.length) {
				pastKnowledgeTables = [...pastKnowledgeTables, ...moreKnowledgeTables.items];
			} else {
				//* Finished loading oldest conversation
				moreKTablesFinished = true;
			}
		} else {
			const responseBody = await response.json();
			if (response.status !== 404) {
				logger.error('ACTIONTBL_LIST_KNOWTBL', responseBody);
			}
			console.error(responseBody.message);
			toast.error('Failed to fetch knowledge tables', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		isLoadingKTables = false;
		isLoadingMoreKTables = false;
	}

	async function refetchTables() {
		if (searchQuery) {
			await handleSearchTables(searchQuery);
		} else {
			searchController?.abort('Duplicate');
			pastKnowledgeTables = [];
			currentOffset = 0;
			moreKTablesFinished = false;
			await getKnowledgeTables();
			isLoadingSearch = false;
		}
	}

	async function handleSearchTables(q: string) {
		isLoadingSearch = true;

		if (!searchQuery) return refetchTables();

		searchController?.abort('Duplicate');
		searchController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/list?${new URLSearchParams({
					limit: limit.toString(),
					search_query: q
				})}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': page.params.project_id ?? ''
					}
				}
			);
			currentOffset = limit;
			moreKTablesFinished = false;

			const responseBody = await response.json();
			if (response.ok) {
				pastKnowledgeTables = responseBody.items;
			} else {
				logger.error('ACTIONTBL_LIST_SEARCHKNOWTBL', responseBody);
				console.error(responseBody);
				toast.error('Failed to search tables', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}
			isLoadingSearch = false;
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
				isLoadingSearch = false;
			}
		}
	}
	const debouncedSearchTables = debounce(handleSearchTables, 300);

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !isLoadingMoreKTables && !moreKTablesFinished) {
			await getKnowledgeTables();
		}
	};
</script>

<Dialog.Root bind:open={isSelectingKnowledgeTable}>
	<Dialog.Content class="h-[90vh] w-full bg-[#FAFBFC] data-dark:bg-[#1E2024] sm:w-[80vw]">
		<Dialog.Header>Choose Knowledge Table(s)</Dialog.Header>

		<div class="items mb-3 flex justify-between gap-1 px-4 pt-3 sm:px-6">
			<SearchBar
				bind:searchQuery
				{isLoadingSearch}
				debouncedSearch={debouncedSearchTables}
				label="Search table"
				placeholder="Search table"
			/>

			<Button
				aria-label="Create table"
				onclick={() => (isAddingTable = true)}
				class="relative mr-1 flex aspect-square h-min w-min flex-[0_0_auto] items-center justify-center gap-1.5 place-self-end px-2 py-2 text-xs sm:mr-0.5 sm:aspect-auto sm:px-3 sm:text-sm lg:place-self-center"
			>
				<AddIcon class="h-3.5 w-3.5" />
				<span class="hidden sm:block">Create table</span>
			</Button>
		</div>

		<div
			onscroll={debounce(scrollHandler, 300)}
			style="grid-auto-rows: 112px;"
			class="grid h-[calc(100vh-4.25rem)] grid-flow-row grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] gap-2 overflow-auto px-4 pb-3 sm:px-6"
		>
			{#if isLoadingKTables}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 rounded-lg bg-black/[0.09] data-dark:bg-white/[0.1]"
					/>
				{/each}
			{:else}
				{#each pastKnowledgeTables as knowledgeTable}
					<button
						onclick={() => {
							selectedKnowledgeTables = knowledgeTable.id;
							isSelectingKnowledgeTable = false;
						}}
						title={knowledgeTable.id}
						class="flex flex-col rounded-lg border border-[#E5E5E5] bg-white data-dark:border-[#333] data-dark:bg-[#42464E]"
					>
						<div
							class="flex w-full grow items-start border-b border-[#E5E5E5] p-3 data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1">
								<KnowledgeTableIcon class="h-5 w-5 flex-[0_0_auto] text-[#475467]" />
								<span class="line-clamp-2 break-all text-sm text-[#344054]">
									{knowledgeTable.id}
								</span>
							</div>
						</div>

						<div class="flex px-3 py-2">
							<span
								title={new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
								class="line-clamp-1 text-xs font-medium text-[#98A2B3] data-dark:text-[#C9C9C9]"
							>
								Last updated
								<span class="text-[#475467]">
									{new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
										month: 'long',
										day: 'numeric',
										year: 'numeric'
									})}
								</span>
							</span>
						</div>
					</button>
				{/each}

				{#if isLoadingMoreKTables}
					<div class="mx-auto flex items-center justify-center p-4">
						<LoadingSpinner class="h-5 w-5 text-secondary" />
					</div>
				{/if}
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<AddTableDialog uploadFile bind:isAddingTable {refetchTables} />
