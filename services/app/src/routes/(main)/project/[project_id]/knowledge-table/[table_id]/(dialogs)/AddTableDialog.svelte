<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { pastKnowledgeTables } from '../../knowledgeTablesStore';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let isAddingTable: boolean;

	let tableId = '';
	let selectedModel = '';

	let isLoading = false;

	$: if (!isAddingTable) {
		tableId = '';
	}

	async function handleAddTable() {
		if (!tableId) return alert('Table ID is required');

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				id: tableId,
				cols: [],
				embedding_model: selectedModel
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_TBL_ADD', responseBody);
			alert('Failed to add table: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			//TODO: Consider invalidating fetch request instead
			$pastKnowledgeTables = [
				{
					id: tableId,
					cols: [],
					lock_till: 0,
					updated_at: new Date().toISOString(),
					indexed_at_fts: null,
					indexed_at_sca: null,
					indexed_at_vec: null,
					parent_id: null,
					title: ''
				},
				...$pastKnowledgeTables
			];
			isAddingTable = false;
			tableId = '';
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={isAddingTable}>
	<Dialog.Content class="min-w-[25rem]">
		<Dialog.Header>New knowledge table</Dialog.Header>

		<div class="grow py-3 w-full overflow-auto">
			<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Table ID
				</span>

				<input
					type="text"
					bind:value={tableId}
					class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<div class="flex flex-col gap-1 px-6 pl-8 py-2">
				<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Embedding Model
				</span>

				<ModelSelect
					capabilityFilter="embed"
					sameWidth={true}
					bind:selectedModel
					buttonText={selectedModel || 'Select model'}
				/>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isAddingTable = false)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					on:click={handleAddTable}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
