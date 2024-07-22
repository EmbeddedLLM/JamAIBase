<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import logger from '$lib/logger';
	import {
		pastActionTables,
		pastKnowledgeTables,
		pastChatAgents,
		pastChatConversations
	} from '../tablesStore';

	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let isDeletingTable: string | null;
	export let deletedCb: ((success: boolean) => any) | undefined = undefined;

	let isLoading = false;

	async function handleDeleteTable() {
		if (isLoading || !isDeletingTable) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${isDeletingTable}`,
			{
				method: 'DELETE'
			}
		);
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_DELETETBL`), responseBody);
			toast.error('Failed to delete table', {
				description: responseBody.message || JSON.stringify(responseBody)
			});

			if (deletedCb) deletedCb(false);
		} else {
			switch (tableType) {
				case 'action': {
					$pastActionTables = $pastActionTables.filter((t) => t.id !== isDeletingTable);
					if ($page.params.table_id === isDeletingTable) {
						goto(
							`/project/${$page.params.project_id}/action-table/${$pastActionTables[0]?.id || ''}`
						);
					}
					break;
				}
				case 'knowledge': {
					$pastKnowledgeTables = $pastKnowledgeTables.filter(
						(table) => table.id !== isDeletingTable
					);
					if ($page.params.table_id === isDeletingTable) {
						goto(
							`/project/${$page.params.project_id}/knowledge-table/${$pastKnowledgeTables[0]?.id || ''}`
						);
					}
					break;
				}
				case 'chat': {
					$pastChatAgents = $pastChatAgents.filter((t) => t.id !== isDeletingTable);
					$pastChatConversations = $pastChatConversations.filter((t) => t.id !== isDeletingTable);
					if ($page.params.table_id === isDeletingTable) {
						goto(
							`/project/${$page.params.project_id}/chat-table/${$pastChatConversations[0]?.id || ''}`
						);
					}
					break;
				}
				default:
					break;
			}
			isDeletingTable = null;

			if (deletedCb) deletedCb(true);
		}

		isLoading = false;
	}
</script>

<Dialog.Root
	open={!!isDeletingTable}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingTable = null;
		}
	}}
>
	<Dialog.Content class="w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to delete table
				<span class="font-medium text-black data-dark:text-white">`{isDeletingTable}`</span>? This
				process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleDeleteTable}
					variant="destructive"
					type="button"
					loading={isLoading}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
