<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import throttle from 'lodash/throttle';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { pastChatAgents, pastChatConversations } from '../../chatTablesStore';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	const { PUBLIC_JAMAI_URL } = env;

	export let isAddingConversation: boolean;
	export let selectedAgent = '';
	export let filteredConversations: typeof $pastChatAgents | undefined = undefined;

	let isLoading = false;
	let availableChatAgents: typeof $pastChatAgents = [];

	let conversationName = '';

	onMount(() => {
		getChatAgents();
	});

	async function getChatAgents() {
		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` +
				new URLSearchParams({
					parent_id: '_agent_'
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);

		if (response.status == 200) {
			const moreChatAgents = await response.json();
			if (moreChatAgents.items.length) {
				availableChatAgents = moreChatAgents.items;
			}
		} else {
			const responseBody = await response.json();
			logger.error('CHATTBL_LIST_AGENTS', responseBody);
			console.error(responseBody.message);
		}
	}
	const throttledInvalidateAgents = throttle(getChatAgents, 5000);

	async function handleAddConversation() {
		if (!conversationName || !selectedAgent) {
			return alert('Please fill in all fields');
		}

		isLoading = true;

		const response = await fetch(
			`/api/v1/gen_tables/chat/duplicate/${selectedAgent}/${conversationName}?` +
				new URLSearchParams({
					deploy: 'true'
				}),
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				}
			}
		);

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('CHATTBL_CONV_ADD', responseBody);
			alert(
				'Failed to add conversation: ' + (responseBody.message || JSON.stringify(responseBody))
			);
		} else {
			$pastChatConversations = [
				{
					id: conversationName,
					cols: [],
					lock_till: 0,
					updated_at: new Date().toISOString(),
					indexed_at_fts: null,
					indexed_at_sca: null,
					indexed_at_vec: null,
					parent_id: selectedAgent,
					title: ''
				},
				...$pastChatConversations
			];
			isAddingConversation = false;

			if (filteredConversations) {
				filteredConversations = [
					...filteredConversations,
					{
						id: conversationName,
						cols: [],
						lock_till: 0,
						updated_at: new Date().toISOString(),
						indexed_at_fts: null,
						indexed_at_sca: null,
						indexed_at_vec: null,
						parent_id: selectedAgent,
						title: ''
					}
				];
			}
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={isAddingConversation}>
	<Dialog.Content class="min-w-[25rem]">
		<Dialog.Header>New conversation</Dialog.Header>

		<div class="grow py-3 w-full overflow-auto">
			<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Conversation ID
				</span>

				<input
					type="text"
					bind:value={conversationName}
					class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<div class="flex flex-col gap-1 px-6 pl-8 py-2">
				<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Agent
				</span>

				<Select.Root>
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div on:mouseenter={throttledInvalidateAgents} on:focusin={throttledInvalidateAgents}>
						<Select.Trigger asChild let:builder>
							<Button
								builders={[builder]}
								variant="outline"
								class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
							>
								<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
									{selectedAgent || 'Select Chat Agent'}
								</span>

								<ChevronDown class="h-4 w-4" />
							</Button>
						</Select.Trigger>
					</div>
					<Select.Content side="bottom" class="max-h-96 overflow-y-auto">
						{#each availableChatAgents as chatTable}
							<Select.Item
								on:click={() => (selectedAgent = chatTable.id)}
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
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isAddingConversation = false)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					on:click={handleAddConversation}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
