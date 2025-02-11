<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import { Dialog as DialogPrimitive } from 'bits-ui';
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

	export let isSelectingKnowledgeTable: boolean;
	export let selectedKnowledgeTables: string; //TODO: Add type

	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let pastKnowledgeTables: GenTable[] = [];
	let isAddingTable = false;

	let isLoadingKTables = true;
	let isLoadingMoreKTables = false;
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
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?` +
				new URLSearchParams({
					offset: currentOffset.toString(),
					limit: limit.toString()
				}),
			{
				credentials: 'same-origin',
				headers: {
					'x-project-id': $page.params.project_id
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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?${new URLSearchParams({
					limit: limit.toString(),
					search_query: q
				})}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': $page.params.project_id
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
	<Dialog.Content class="w-full sm:w-[80vw] h-[90vh] bg-[#FAFBFC] data-dark:bg-[#1E2024]">
		<Dialog.Header>Choose Knowledge Table(s)</Dialog.Header>

		<div class="flex items justify-between mb-3 px-4 sm:px-6 pt-3">
			<SearchBar
				bind:searchQuery
				{isLoadingSearch}
				debouncedSearch={debouncedSearchTables}
				label="Search table"
				placeholder="Search table"
			/>

			<Button
				aria-label="Create table"
				on:click={() => (isAddingTable = true)}
				class="place-self-end lg:place-self-center flex-[0_0_auto] relative flex items-center justify-center gap-1.5 mr-1 sm:mr-0.5 px-2 sm:px-3 py-2 h-min w-min text-xs sm:text-sm aspect-square sm:aspect-auto"
			>
				<AddIcon class="h-3.5 w-3.5" />
				<span class="hidden sm:block">Create table</span>
			</Button>
		</div>

		<div
			on:scroll={debounce(scrollHandler, 300)}
			style="grid-auto-rows: 112px;"
			class="grid grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] grid-flow-row gap-2 px-4 sm:px-6 pb-3 h-[calc(100vh-4.25rem)] overflow-auto"
		>
			{#if isLoadingKTables}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
					/>
				{/each}
			{:else}
				{#each pastKnowledgeTables as knowledgeTable}
					<button
						on:click={() => {
							selectedKnowledgeTables = knowledgeTable.id;
							isSelectingKnowledgeTable = false;
						}}
						title={knowledgeTable.id}
						class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
					>
						<div
							class="grow flex items-start p-3 w-full border-b border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1">
								<KnowledgeTableIcon class="flex-[0_0_auto] h-5 w-5 text-[#475467]" />
								<span class="text-sm text-[#344054] break-all line-clamp-2">
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
								class="font-medium text-xs text-[#98A2B3] data-dark:text-[#C9C9C9] line-clamp-1"
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
					<div class="flex items-center justify-center mx-auto p-4">
						<LoadingSpinner class="h-5 w-5 text-secondary" />
					</div>
				{/if}
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<AddTableDialog uploadFile bind:isAddingTable {refetchTables} />
