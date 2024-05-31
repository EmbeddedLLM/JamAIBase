<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import logger from '$lib/logger';
	import type { ActionTable } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Dialog from '$lib/components/ui/dialog';
	import RowIcon from '$lib/icons/RowIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let isSelectingKnowledgeTable: boolean;
	export let selectedKnowledgeTables: string; //TODO: Add type

	let pastKnowledgeTables: ActionTable[] = [];

	let isLoadingMoreKTables = true; //TODO: Figure out infinite loop / pagination here
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
				pastKnowledgeTables = [...pastKnowledgeTables, ...moreKnowledgeTables.items];
			} else {
				//* Finished loading oldest conversation
				moreKTablesFinished = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_LIST_KNOWTBL', responseBody);
			console.error(responseBody.message);
		}

		isLoadingMoreKTables = false;
	}
</script>

<Dialog.Root bind:open={isSelectingKnowledgeTable}>
	<Dialog.Content class="min-w-[80vw] h-[90vh]">
		<Dialog.Header>Choose Knowledge Table(s)</Dialog.Header>

		<div
			style="grid-auto-rows: 112px;"
			class="grid grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5 grid-flow-row gap-4 p-6 h-[calc(100vh-4.25rem)] bg-[#FAFBFC] data-dark:bg-[#1E2024] overflow-auto"
		>
			{#if isLoadingMoreKTables}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
					/>
				{/each}
			{:else}
				{#each pastKnowledgeTables as knowledgeTable (knowledgeTable.id)}
					<button
						on:click={() => {
							selectedKnowledgeTables = knowledgeTable.id;
							isSelectingKnowledgeTable = false;
						}}
						title={knowledgeTable.id}
						class="flex flex-col border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
					>
						<div
							class="grow flex items-start p-3 w-full border-b border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1.5">
								<RowIcon class="flex-[0_0_auto] h-5 w-5 text-[#4169E1]" />
								<span class="font-medium text-sm text-left break-all line-clamp-2">
									{knowledgeTable.id}
								</span>
							</div>
						</div>

						<div class="flex p-3">
							<span
								title={new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
								class="text-xs text-[#999] data-dark:text-[#C9C9C9] line-clamp-1"
							>
								Updated at: {new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
							</span>
						</div>
					</button>
				{/each}
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button
					variant="link"
					type="button"
					on:click={() => (isSelectingKnowledgeTable = false)}
					class="grow px-6"
				>
					Cancel
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
