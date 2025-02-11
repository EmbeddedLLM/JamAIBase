<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import {
		pastActionTables,
		pastChatAgents,
		pastKnowledgeTables
	} from '$lib/components/tables/tablesStore';
	import logger from '$lib/logger';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let isEditingTableID: string | null;
	export let editedCb: ((success: boolean, tableID?: string) => any) | undefined = undefined;

	let form: HTMLFormElement;
	let isLoadingSaveEdit = false;

	async function handleSaveTableID(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		const editedTableID = e.currentTarget.getElementsByTagName('input')[0].value.trim();

		if (isEditingTableID === editedTableID) return;

		isLoadingSaveEdit = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rename/${isEditingTableID}/${editedTableID}`,
			{
				method: 'POST',
				headers: {
					'x-project-id': $page.params.project_id
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

					if ($page.params.table_id === isEditingTableID) {
						goto(`/project/${$page.params.project_id}/action-table/${editedTableID}`);
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

					if ($page.params.table_id === isEditingTableID) {
						goto(`/project/${$page.params.project_id}/knowledge-table/${editedTableID}`);
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

					if ($page.params.table_id === isEditingTableID) {
						goto(`/project/${$page.params.project_id}/chat-table/${editedTableID}`);
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

<Dialog.Root
	open={!!isEditingTableID}
	onOpenChange={(e) => {
		if (!e) {
			isEditingTableID = null;
		}
	}}
>
	<Dialog.Content data-testid="rename-table-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Edit table ID</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={form}
			on:submit|preventDefault={handleSaveTableID}
			class="grow w-full overflow-auto"
		>
			<div class="flex flex-col gap-1 px-4 sm:px-6 py-3 h-full w-full text-center">
				<span class="font-medium text-left text-xs sm:text-sm text-black"> Table ID* </span>

				<InputText value={isEditingTableID} name="table_id" placeholder="Required" />
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingSaveEdit} class="hidden">Save</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={() => form.requestSubmit()}
					loading={isLoadingSaveEdit}
					disabled={isLoadingSaveEdit}
					class="relative grow px-6 rounded-full"
				>
					Save
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
