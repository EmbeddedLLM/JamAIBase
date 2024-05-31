<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import debounce from 'lodash/debounce';
	import { pastActionTables } from './actionTablesStore';
	import logger from '$lib/logger';

	import AddTableDialog from './[table_id]/(dialogs)/AddTableDialog.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	let isLoadingMoreATables = true; //TODO: Figure out infinite loop / pagination here
	let moreATablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	let isAddingTable = false;

	onMount(() => {
		getActionTables();

		return () => {
			$pastActionTables = [];
		};
	});

	async function getActionTables() {
		isLoadingMoreATables = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action?` +
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
			const moreActionTables = await response.json();
			if (moreActionTables.items.length) {
				$pastActionTables = [...$pastActionTables, ...moreActionTables.items];
			} else {
				//* Finished loading oldest conversation
				moreATablesFinished = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_LIST_TBL', responseBody);
			console.error(responseBody.message);
		}

		isLoadingMoreATables = false;
	}

	//* Load more conversations when scrolling down
	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !isLoadingMoreATables && !moreATablesFinished) {
			await getActionTables();
		}
	};
</script>

<svelte:head>
	<title>Action Table</title>
</svelte:head>

<div
	on:scroll={debounce(scrollHandler, 400)}
	style="grid-auto-rows: 112px;"
	class="grid grid-cols-2 lg:grid-cols-4 2xl:grid-cols-6 grid-flow-row gap-4 p-6 h-[calc(100vh-4.25rem)] bg-[#FAFBFC] data-dark:bg-[#1E2024] overflow-auto"
>
	<button
		on:click={() => (isAddingTable = true)}
		class="flex flex-col items-center justify-center gap-2 bg-secondary/[0.12] rounded-lg"
	>
		<div class="flex items-center justify-center h-8 bg-secondary rounded-full aspect-square">
			<AddIcon class="h-4 w-4 text-white" />
		</div>

		<span class="font-medium text-sm"> New Action Table </span>
	</button>

	{#if isLoadingMoreATables}
		{#each Array(12) as _}
			<Skeleton
				class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
			/>
		{/each}
	{:else}
		{#each $pastActionTables as actionTable (actionTable.id)}
			<a
				href={`/project/${$page.params.project_id}/action-table/${actionTable.id}`}
				title={actionTable.id}
				class="flex flex-col border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
			>
				<div class="grow flex items-start p-3 border-b border-[#E5E5E5] data-dark:border-[#333]">
					<div class="flex items-start gap-1.5">
						<ActionTableIcon class="flex-[0_0_auto] h-5 w-5 text-secondary -translate-y-0.5" />
						<span class="font-medium text-sm break-all line-clamp-2">{actionTable.id}</span>
					</div>
				</div>

				<div class="flex p-3">
					<span
						title={new Date(actionTable.updated_at).toLocaleString(undefined, {
							month: 'long',
							day: 'numeric',
							year: 'numeric'
						})}
						class="text-xs text-[#999] data-dark:text-[#C9C9C9] line-clamp-1"
					>
						Updated at: {new Date(actionTable.updated_at).toLocaleString(undefined, {
							month: 'long',
							day: 'numeric',
							year: 'numeric'
						})}
					</span>
				</div>
			</a>
		{/each}
	{/if}
</div>

<AddTableDialog bind:isAddingTable />
