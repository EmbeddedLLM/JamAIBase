<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { pastChatAgents } from '$lib/components/tables/tablesStore';
	import { tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	export let isAddingConversation: boolean;
	export let filterByAgent: string;
	export let filteredConversations: typeof $pastChatAgents | undefined = undefined;
	export let refetchTables: ((tableID: string) => Promise<void>) | undefined = undefined;

	let isLoading = false;

	let conversationName = '';
	let conversationAgent = '';

	$: if (filterByAgent !== '_chat_') conversationAgent = filterByAgent;

	async function handleAddConversation() {
		if (!conversationAgent) return toast.error('Agent not selected', { id: 'agent-not-selected' });

		if (conversationName?.trim() && !tableIDPattern.test(conversationName))
			return toast.error(
				'Conversation ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'conversation-id-invalid' }
			);

		isLoading = true;

		const searchParams = new URLSearchParams({
			create_as_child: 'true'
		});
		if (conversationName) {
			searchParams.append('table_id_dst', conversationName);
		}

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/duplicate/${conversationAgent}?` + searchParams,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': $page.params.project_id
				}
			}
		);

		const responseBody = await response.json();
		if (!response.ok) {
			logger.error('CHATTBL_CONV_ADD', responseBody);
			toast.error('Failed to add conversation', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		} else {
			if (refetchTables) {
				await refetchTables(responseBody.id);
				isAddingConversation = false;
				isLoading = false;
			} else {
				goto(`/project/${$page.params.project_id}/chat-table/${responseBody.id}`);
			}
		}
	}
</script>

<Dialog.Root
	bind:open={isAddingConversation}
	onOpenChange={(e) => {
		if (!e && filterByAgent !== '_chat_') {
			conversationAgent = filterByAgent;
		}
	}}
>
	<Dialog.Content data-testid="new-conv-dialog" class="w-[clamp(0px,30rem,100%)]">
		<Dialog.Header>New conversation</Dialog.Header>

		<form
			on:submit|preventDefault={handleAddConversation}
			class="grow flex flex-col gap-3 py-3 w-full overflow-auto"
		>
			<div class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center">
				<label for="conversation-id" class="font-medium text-left text-xs sm:text-sm text-black">
					Conversation ID
				</label>

				<InputText bind:value={conversationName} name="conversation-id" placeholder="Optional" />
			</div>

			<div class="flex flex-col gap-1 px-4 sm:px-6">
				<span class="font-medium text-left text-xs sm:text-sm text-black"> Agent* </span>

				<Select.Root
					selected={{ value: conversationAgent }}
					onSelectedChange={(v) => {
						if (v) {
							conversationAgent = v.value;
						}
					}}
				>
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div>
						<Select.Trigger asChild let:builder>
							<Button
								disabled={!filteredConversations}
								builders={[builder]}
								title="Select Chat Agent"
								variant="outline-neutral"
								class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full {!conversationAgent
									? 'italic text-muted-foreground'
									: ''} bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent rounded-md"
							>
								<span class="w-full whitespace-nowrap line-clamp-1 font-normal text-left">
									{conversationAgent || 'Select Chat Agent'}
								</span>

								<ChevronDown class="h-4 w-4" />
							</Button>
						</Select.Trigger>
					</div>
					<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
						{#each $pastChatAgents as chatTable}
							<Select.Item
								value={chatTable.id}
								label={chatTable.id}
								class="flex justify-between gap-10 cursor-pointer"
							>
								{chatTable.id}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoading}
				disabled={isLoading}
				class="hidden relative grow px-6 rounded-full"
			>
				Add
			</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleAddConversation}
					type="button"
					loading={isLoading}
					disabled={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
