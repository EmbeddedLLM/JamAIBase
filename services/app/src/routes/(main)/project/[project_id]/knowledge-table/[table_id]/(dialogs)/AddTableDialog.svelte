<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { pastKnowledgeTables } from '../../../tablesStore';
	import { idPattern } from '$lib/constants';
	import logger from '$lib/logger';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	export let isAddingTable: boolean;

	let tableId = '';
	let selectedModel = '';

	let isLoading = false;

	$: if (!isAddingTable) {
		tableId = '';
	}

	async function handleAddTable() {
		if (!tableId) return toast.error('Table ID is required');
		if (!selectedModel) return toast.error('Model not selected');

		if (!idPattern.test(tableId))
			return toast.error(
				'Table ID must contain only alphanumeric characters and underscores/hyphens, and start and end with alphanumeric characters'
			);

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
			toast.error('Failed to add table', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
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
					Table ID*
				</span>

				<InputText bind:value={tableId} placeholder="Required" />
			</div>

			<div class="flex flex-col gap-1 px-6 pl-8 py-2">
				<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Embedding Model*
				</span>

				<ModelSelect
					capabilityFilter="embed"
					sameWidth={true}
					bind:selectedModel
					buttonText={selectedModel || 'Select model'}
					class={!selectedModel ? 'italic text-muted-foreground' : ''}
				/>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleAddTable}
					type="button"
					loading={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
