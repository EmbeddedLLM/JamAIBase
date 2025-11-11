<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { pastChatAgents } from '$lib/components/tables/tablesState.svelte';
	import { tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	interface Props {
		isAddingConversation: boolean;
		filterByAgent: string;
		filteredConversations?: Omit<GenTable, 'num_rows'>[];
		refetchTables?: (tableID: string) => Promise<void>;
	}

	let {
		isAddingConversation = $bindable(),
		filterByAgent,
		filteredConversations = $bindable(),
		refetchTables = undefined
	}: Props = $props();

	let isLoading = $state(false);

	let conversationName = $state('');
	let conversationAgent = $state('');

	$effect(() => {
		if (filterByAgent !== '_chat_') conversationAgent = filterByAgent;
	});

	async function handleAddConversation() {
		if (!conversationAgent) return toast.error('Agent not selected', { id: 'agent-not-selected' });

		if (conversationName?.trim() && !tableIDPattern.test(conversationName))
			return toast.error(
				'Conversation ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'conversation-id-invalid' }
			);

		isLoading = true;

		const searchParams = new URLSearchParams({
			table_id_src: conversationAgent,
			create_as_child: 'true'
		});
		if (conversationName) {
			searchParams.append('table_id_dst', conversationName);
		}

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/duplicate?` + searchParams,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
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
				goto(`/project/${page.params.project_id}/chat-table/${responseBody.id}`);
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
			onsubmit={(e) => {
				e.preventDefault();
				handleAddConversation();
			}}
			class="flex w-full grow flex-col gap-3 overflow-auto py-3"
		>
			<div class="flex w-full flex-col gap-1 px-4 text-center sm:px-6">
				<Label for="conversation-id" class="text-xs sm:text-sm">Conversation ID</Label>

				<InputText
					bind:value={conversationName}
					id="conversation-id"
					name="conversation-id"
					placeholder="Optional"
				/>
			</div>

			<div class="flex flex-col gap-1 px-4 sm:px-6">
				<Label required class="text-xs sm:text-sm">Agent</Label>

				<Select.Root type="single" bind:value={conversationAgent}>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div>
						<Select.Trigger
							disabled={!filteredConversations}
							title="Select Chat Agent"
							class="flex h-10 min-w-full items-center justify-between gap-8 pl-3 pr-2 {!conversationAgent
								? 'italic text-muted-foreground'
								: ''} border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
						>
							{#snippet children()}
								<span class="line-clamp-1 w-full whitespace-nowrap text-left font-normal">
									{conversationAgent || 'Select Chat Agent'}
								</span>
							{/snippet}
						</Select.Trigger>
					</div>
					<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
						{#each $pastChatAgents as chatTable}
							<Select.Item
								value={chatTable.id}
								label={chatTable.id}
								class="flex cursor-pointer justify-between gap-10"
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
				class="relative hidden grow px-6"
			>
				Add
			</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					onclick={handleAddConversation}
					type="button"
					loading={isLoading}
					disabled={isLoading}
					class="relative grow px-6"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
