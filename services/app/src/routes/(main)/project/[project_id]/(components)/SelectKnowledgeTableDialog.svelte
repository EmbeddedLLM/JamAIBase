<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Dialog from '$lib/components/ui/dialog';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import RowIcon from '$lib/icons/RowIcon.svelte';

	export let isSelectingKnowledgeTable: boolean;
	export let selectedKnowledgeTables: string; //TODO: Add type

	let pastKnowledgeTables: GenTable[] = [];

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
			if (response.status !== 404) {
				logger.error('ACTIONTBL_LIST_KNOWTBL', responseBody);
			}
			console.error(responseBody.message);
			toast.error('Failed to fetch knowledge tables', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
		}

		isLoadingKTables = false;
		isLoadingMoreKTables = false;
	}

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
	<Dialog.Content class="min-w-[80vw] h-[90vh]">
		<Dialog.Header>Choose Knowledge Table(s)</Dialog.Header>

		<div
			on:scroll={debounce(scrollHandler, 300)}
			style="grid-auto-rows: 112px;"
			class="grid grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5 grid-flow-row gap-4 p-6 h-[calc(100vh-4.25rem)] bg-[#FAFBFC] data-dark:bg-[#1E2024] overflow-auto"
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
						class="flex flex-col border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
					>
						<div
							class="grow flex items-start p-3 w-full border-b border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1.5">
								<RowIcon class="flex-[0_0_auto] h-5 w-5 text-secondary" />
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

				{#if isLoadingMoreKTables}
					<div class="flex items-center justify-center mx-auto p-4">
						<LoadingSpinner class="h-5 w-5 text-secondary" />
					</div>
				{/if}
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
