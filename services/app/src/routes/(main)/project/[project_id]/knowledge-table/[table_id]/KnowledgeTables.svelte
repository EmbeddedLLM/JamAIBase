<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { beforeNavigate, goto } from '$app/navigation';
	import { page } from '$app/stores';
	import debounce from 'lodash/debounce';
	import { OverlayScrollbarsComponent } from 'overlayscrollbars-svelte';
	import autoAnimate from '@formkit/auto-animate';
	import { showRightDock } from '$globalStore';
	import { pastKnowledgeTables } from '../knowledgeTablesStore';
	import { timestampsDisplayName } from '$lib/constants';
	import logger from '$lib/logger';
	import type { ActionTable, Timestamp } from '$lib/types';

	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import RowIcon from '$lib/icons/RowIcon.svelte';
	import DeleteIcon from '$lib/icons/DeleteIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let isDeletingTable: string | null;

	let searchResults: ActionTable[] = [];
	let searchQuery: string;
	let isNoResults = false;

	let isLoadingMoreKTables = false;
	let moreKTablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	let isEditingTableID: string | null = null;
	let saveEditBtn: HTMLButtonElement;

	onMount(() => {
		getKnowledgeTables();

		return () => {
			$pastKnowledgeTables = [];
		};
	});

	beforeNavigate(() => (isEditingTableID = null));

	async function getKnowledgeTables() {
		isLoadingMoreKTables = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?` +
				new URLSearchParams({
					offset: currentOffset.toString(),
					limit: limit.toString()
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);
		currentOffset += limit;

		if (response.status == 200) {
			const moreKnowledgeTables = await response.json();
			if (moreKnowledgeTables.items.length) {
				$pastKnowledgeTables = [...$pastKnowledgeTables, ...moreKnowledgeTables.items];
			} else {
				//* Finished loading oldest conversation
				moreKTablesFinished = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('KNOWTBL_LIST_TBL', responseBody);
			console.error(responseBody.message);
		}

		isLoadingMoreKTables = false;
	}

	let timestamps: Timestamp = {
		today: null,
		yesterday: null,
		two_days: null,
		three_days: null,
		last_week: null,
		last_month: null,
		older: null
	};
	let timestampKeys = Object.keys(timestamps) as Array<keyof Timestamp>;
	$: {
		timestampKeys.forEach((key) => (timestamps[key] = null));
		$pastKnowledgeTables.forEach((table, index) => {
			const timeDiff = Date.now() - new Date(table.updated_at).getTime();
			if (timeDiff < 24 * 60 * 60 * 1000) {
				if (timestamps.today == null) {
					timestamps.today = index;
				}
			} else if (timeDiff < 2 * 24 * 60 * 60 * 1000) {
				if (timestamps.yesterday == null) {
					timestamps.yesterday = index;
				}
			} else if (timeDiff < 3 * 24 * 60 * 60 * 1000) {
				if (timestamps.two_days == null) {
					timestamps.two_days = index;
				}
			} else if (timeDiff < 4 * 24 * 60 * 60 * 1000) {
				if (timestamps.three_days == null) {
					timestamps.three_days = index;
				}
			} else if (timeDiff < 2 * 7 * 24 * 60 * 60 * 1000) {
				if (timestamps.last_week == null) {
					timestamps.last_week = index;
				}
			} else if (timeDiff < 30 * 24 * 60 * 60 * 1000) {
				if (timestamps.last_month == null) {
					timestamps.last_month = index;
				}
			} else if (timestamps.older == null) {
				timestamps.older = index;
			}
		});
	}

	function editTableID(tableID: string) {
		isEditingTableID = tableID;
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			((e.target as HTMLElement).parentElement as HTMLFormElement).requestSubmit();
		}
	}

	async function saveTableID(e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }) {
		const editedTableID = (e.currentTarget.childNodes[0] as HTMLTextAreaElement).value.trim();

		const response = await fetch(
			`/api/v1/gen_tables/knowledge/rename/${isEditingTableID}/${editedTableID}`,
			{
				method: 'POST'
			}
		);

		if (response.status == 200) {
			//TODO: Could trigger search again instead of manually removing from search results
			// if (searchResults.length) {
			// 	// Update search results with new title if it exists
			// 	const editedConvSearchIndex = searchResults.findIndex(
			// 		(item) => item.conversation_id == isEditingTitle
			// 	);
			// 	if (editedConvSearchIndex != -1) {
			// 		searchResults[editedConvSearchIndex] = {
			// 			...searchResults[editedConvSearchIndex],
			// 			conversation_id: isEditingTitle!,
			// 			title: editedTitle,
			// 			updated_at: new Date().toISOString()
			// 		};
			// 		searchResults = searchResults;
			// 	}
			// }

			$pastKnowledgeTables = [
				{
					...$pastKnowledgeTables.find((table) => table.id == isEditingTableID)!,
					id: editedTableID,
					updated_at: new Date().toISOString()
				},
				...$pastKnowledgeTables.filter((table) => table.id != isEditingTableID)
			];

			if ($page.params.table_id == isEditingTableID) {
				goto(`/project/${$page.params.project_id}/knowledge-table/${editedTableID}`);
			}

			isEditingTableID = null;
		} else {
			const responseBody = await response.json();
			logger.error('KNOWTBL_RENAME_TBL', responseBody);
			alert(
				'Error while renaming table: ' + (responseBody.message || JSON.stringify(responseBody))
			);
		}
	}

	async function handleSearch() {
		isNoResults = false;

		if (!searchQuery) return (searchResults = []);

		const response = await fetch(
			`/api/table/search?` +
				new URLSearchParams({
					q: searchQuery,
					threshold: '0.05'
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);

		if (response.status == 200) {
			const results = await response.json();

			if (results.length) {
				searchResults = results;
			} else {
				searchResults = [];
				isNoResults = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('KNOWTBL_SEARCH_TABLE', responseBody);
			alert(
				'Error while retrieving search results: ' +
					(responseBody.message || JSON.stringify(responseBody))
			);
		}
	}

	//* Load more conversations when scrolling down
	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !isLoadingMoreKTables && !moreKTablesFinished) {
			await getKnowledgeTables();
		}
	};
</script>

<span class="flex items-center gap-2 mx-6 text-sm text-[#999999]">Table history</span>

<div inert={!$showRightDock || null} class="relative mx-6">
	<SearchIcon class="absolute top-1/2 left-3 -translate-y-1/2 h-6 w-6" />
	<input
		name="search-knowledge-tables"
		placeholder="Search"
		bind:value={searchQuery}
		on:input={debounce(handleSearch, 400)}
		class="flex px-12 py-2 h-11 w-full rounded-lg border data-dark:border border-transparent data-dark:border-[#42464E] ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors bg-[#F4F5FA] data-dark:bg-transparent"
	/>
	{#if searchQuery}
		<button
			on:click={() => {
				searchQuery = '';
				handleSearch();
			}}
			class="absolute top-1/2 right-4 -translate-y-1/2"
		>
			<CloseIcon class="h-5" />
		</button>
	{/if}
</div>

{#if searchResults.length || isNoResults}
	{#if isNoResults}
		<div class="flex items-center justify-center h-20">
			<span class="text-foreground-content/60">No results found</span>
		</div>
	{:else}
		<span class="px-6 py-2 pt-4 text-sm">
			Search results:
			<span class="italic">{searchQuery}</span>
		</span>

		<hr class="w-[calc(100%_+_1.5rem)] -translate-x-3 border-[#454545]" />
	{/if}
{/if}

<OverlayScrollbarsComponent
	inert={!$showRightDock || null}
	defer
	data-pw="knowledge-tables"
	events={{ scroll: (instance, e) => debounce(scrollHandler, 300)(e) }}
	on:osInitialized={(e) => autoAnimate(e.detail[0].elements().viewport)}
	class="grow flex flex-col ml-6 mb-6 pr-6 rounded-md overflow-auto os-dark"
>
	{#each !searchResults.length && !isNoResults ? $pastKnowledgeTables : searchResults as knowledgeTable, index (knowledgeTable.id)}
		{#if knowledgeTable && knowledgeTable.id}
			{#if !searchResults.length && !isNoResults}
				{#each timestampKeys as time (time)}
					{#if timestamps[time] == index}
						<div class="my-2">
							<span class="text-sm text-[#999] font-semibold">
								{timestampsDisplayName[time]}
							</span>
						</div>
					{/if}
				{/each}
			{/if}
			{#if isEditingTableID == knowledgeTable.id}
				<div
					class="relative flex my-2 px-3 py-2 bg-[#F5F5F5] data-dark:bg-[#444951] text-left transition-colors duration-75 rounded-lg group/item"
				>
					<form on:submit|preventDefault={saveTableID} class="flex w-full">
						<!-- svelte-ignore a11y-autofocus -->
						<textarea
							autofocus
							rows="3"
							name="edited-table"
							value={$pastKnowledgeTables.find((table) => table.id == isEditingTableID)?.id}
							on:keydown={interceptSubmit}
							on:blur={(e) => {
								if (e.relatedTarget != saveEditBtn) isEditingTableID = null;
							}}
							class="mr-12 w-full bg-transparent resize-none outline-none text-sm"
						/>

						<button
							bind:this={saveEditBtn}
							title="Save table name"
							type="submit"
							class="absolute top-1.5 right-7 p-1 group/button"
						>
							<CheckIcon
								class="h-5 w-5 stroke-current group-hover/button:stroke-text/50 transition-[stroke] duration-75"
							/>
						</button>
						<button
							title="Cancel edit"
							type="button"
							class="absolute top-1.5 right-1 p-1 group/button"
						>
							<CloseIcon
								class="h-5 w-5 [&_path]:stroke-current group-hover/button:[&_path]:stroke-text/50 transition-[stroke] duration-75"
							/>
						</button>
					</form>
				</div>
			{:else}
				<a
					data-pw="knowledge-table"
					title={knowledgeTable.id}
					href={`/project/${$page.params.project_id}/knowledge-table/${knowledgeTable.id}`}
					class={`relative flex items-center p-2 text-left ${
						$page.params.table_id == knowledgeTable.id &&
						'data-dark:text-foreground-content bg-[#F5F5F5] data-dark:bg-[#444951]'
					} hover:bg-[#F5F5F5] data-dark:hover:bg-[#444951] transition-colors duration-75 rounded-lg group/item`}
				>
					<RowIcon class="h-7 mr-2" />

					<div class="relative flex grow w-full overflow-hidden">
						<span class="line-clamp-1 text-sm">
							{knowledgeTable.id}
						</span>
						<div
							class={`absolute right-0 h-full w-16 bg-gradient-to-l from-[#F5F5F5] data-dark:from-[#444951] from-75% ${
								$page.params.table_id == knowledgeTable.id ? 'opacity-100' : 'opacity-0'
							} group-hover/item:opacity-100 transition-opacity duration-75`}
						/>
					</div>

					<button
						title="Edit table name"
						on:click|preventDefault={() => editTableID(knowledgeTable.id)}
						class={`group/button absolute top-1/2 right-6 p-2 -translate-y-1/2 min-w-[2rem] ${
							$page.params.table_id == knowledgeTable.id ? 'block' : 'hidden'
						} group-hover/item:block`}
					>
						<EditIcon
							class="h-6 group-hover/button:[&>*]:fill-text/50 [&>*]:transition-[fill] [&>*]:duration-75"
						/>
					</button>
					<button
						title="Delete table"
						on:click|preventDefault={() => (isDeletingTable = knowledgeTable.id)}
						class={`group/button absolute top-1/2 right-0 p-2 -translate-y-1/2 min-w-[2rem] ${
							$page.params.table_id == knowledgeTable.id ? 'block' : 'hidden'
						} group-hover/item:block`}
					>
						<DeleteIcon
							class="h-6 group-hover/button:[&>*]:fill-text/50 [&>*]:transition-[fill] [&>*]:duration-75"
						/>
					</button>
				</a>
			{/if}
		{/if}
	{/each}
	{#if isLoadingMoreKTables}
		<div class="flex items-center justify-center mx-auto p-4">
			<LoadingSpinner class="h-5 w-5 text-[#4169e1] data-dark:text-[#5b7ee5]" />
		</div>
	{/if}
</OverlayScrollbarsComponent>
