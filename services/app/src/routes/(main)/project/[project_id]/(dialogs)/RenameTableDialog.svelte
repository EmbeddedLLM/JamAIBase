<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		pastActionTables,
		pastChatAgents,
		pastKnowledgeTables
	} from '$lib/components/tables/tablesState.svelte';
	import logger from '$lib/logger';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		isEditingTableID: string | null;
		editedCb?: ((success: boolean, tableID?: string) => any) | undefined;
	}

	let { tableType, isEditingTableID = $bindable(), editedCb = undefined }: Props = $props();

	let isLoadingSaveEdit = $state(false);

	async function handleSaveTableID(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();
		if (!isEditingTableID) return;

		const editedTableID = e.currentTarget.getElementsByTagName('input')[0].value.trim();
		if (isEditingTableID === editedTableID) return;

		isLoadingSaveEdit = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/rename?${new URLSearchParams([
				['table_id_src', isEditingTableID],
				['table_id_dst', editedTableID]
			])}`,
			{
				method: 'POST',
				headers: {
					'x-project-id': page.params.project_id
				}
			}
		);

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_RENAMETBL`), responseBody);
			toast.error('Failed to rename table', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			if (editedCb) editedCb(false);
		} else {
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

			switch (tableType) {
				case 'action': {
					const index = $pastActionTables.findIndex((table) => table.id === isEditingTableID);
					if (index !== -1) {
						$pastActionTables.unshift({
							...$pastActionTables.splice(index, 1)[0],
							id: editedTableID,
							updated_at: new Date().toISOString()
						});
						$pastActionTables = $pastActionTables;
					}

					if (page.params.table_id === isEditingTableID) {
						goto(`/project/${page.params.project_id}/action-table/${editedTableID}`);
					}
					break;
				}
				case 'knowledge': {
					const index = $pastKnowledgeTables.findIndex((table) => table.id === isEditingTableID);
					if (index !== -1) {
						$pastKnowledgeTables.unshift({
							...$pastKnowledgeTables.splice(index, 1)[0],
							id: editedTableID,
							updated_at: new Date().toISOString()
						});
						$pastKnowledgeTables = $pastKnowledgeTables;
					}

					if (page.params.table_id === isEditingTableID) {
						goto(`/project/${page.params.project_id}/knowledge-table/${editedTableID}`);
					}
					break;
				}
				case 'chat': {
					const indexAgents = $pastChatAgents.findIndex((table) => table.id === isEditingTableID);
					if (indexAgents !== -1) {
						$pastChatAgents.unshift({
							...$pastChatAgents.splice(indexAgents, 1)[0],
							id: editedTableID,
							updated_at: new Date().toISOString()
						});
						$pastChatAgents = $pastChatAgents;
					}

					if (page.params.table_id === isEditingTableID) {
						goto(`/project/${page.params.project_id}/chat-table/${editedTableID}`);
					}
					break;
				}
				default:
					break;
			}

			if (editedCb) editedCb(true, editedTableID);

			isEditingTableID = null;
		}

		isLoadingSaveEdit = false;
	}
</script>

<Dialog.Root bind:open={() => !!isEditingTableID, () => (isEditingTableID = null)}>
	<Dialog.Content data-testid="rename-table-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Edit table ID</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form id="renameTable" onsubmit={handleSaveTableID} class="w-full grow overflow-auto">
			<div class="flex h-full w-full flex-col gap-1 px-4 py-3 text-center sm:px-6">
				<Label required for="table_id" class="text-xs sm:text-sm">Table ID</Label>

				<InputText value={isEditingTableID} id="table_id" name="table_id" placeholder="Required" />
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="renameTable"
					loading={isLoadingSaveEdit}
					disabled={isLoadingSaveEdit}
					class="relative grow px-6"
				>
					Save
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
