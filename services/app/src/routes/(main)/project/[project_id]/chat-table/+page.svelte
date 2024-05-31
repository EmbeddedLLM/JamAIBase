<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { pastChatAgents, pastChatConversations } from './chatTablesStore';
	import logger from '$lib/logger';

	import { AddAgentDialog, AddConversationDialog, DeleteDialogs } from './[table_id]/(dialogs)';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import DeleteIcon from '$lib/icons/DeleteIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	let selectedFilter: 'agents' | 'all' = 'agents';
	let filterByAgent = '';
	let isLoadingFilteredConversations = false;
	let filteredConversations: typeof $pastChatAgents = [];

	let isLoadingMoreCAgents = true;
	let moreCAgentsFinished = false;
	let currentOffsetAgents = 0;
	const limitAgents = 100;

	let isLoadingMoreCConv = true;
	let moreCConvFinished = false;
	let currentOffsetConv = 0;
	const limitConv = 100;

	let isAddingAgent = false;
	let isAddingConversation = false;
	let selectedAgent = '';
	let isDeletingTable: string | null = null;

	onMount(() => {
		getChatAgents();
		getChatConv();

		return () => {
			$pastChatAgents = [];
			$pastChatConversations = [];
		};
	});

	async function getChatAgents() {
		isLoadingMoreCAgents = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` +
				new URLSearchParams({
					offset: currentOffsetAgents.toString(),
					limit: limitAgents.toString(),
					parent_id: '_agent_'
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);
		currentOffsetAgents += limitAgents;

		if (response.status == 200) {
			const moreChatAgents = await response.json();
			if (moreChatAgents.items.length) {
				$pastChatAgents = [...$pastChatAgents, ...moreChatAgents.items];
			} else {
				//* Finished loading oldest conversation
				moreCAgentsFinished = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('CHATTBL_LIST_AGENT', responseBody);
			alert(
				'Failed to fetch chat agents: ' + (responseBody.message || JSON.stringify(responseBody))
			);
		}

		isLoadingMoreCAgents = false;
	}

	async function getChatConv() {
		isLoadingMoreCConv = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` +
				new URLSearchParams({
					offset: currentOffsetConv.toString(),
					limit: limitConv.toString(),
					parent_id: '_chat_'
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);
		currentOffsetConv += limitConv;

		if (response.status == 200) {
			const moreChatConv = await response.json();
			if (moreChatConv.items.length) {
				$pastChatConversations = [...$pastChatConversations, ...moreChatConv.items];
			} else {
				//* Finished loading oldest conversation
				moreCConvFinished = true;
			}
		} else {
			const responseBody = await response.json();
			logger.error('CHATTBL_LIST_CONV', responseBody);
			alert(
				'Failed to fetch chat conversations: ' +
					(responseBody.message || JSON.stringify(responseBody))
			);
		}

		isLoadingMoreCConv = false;
	}

	async function handleFilterByAgent(agentId: string) {
		isLoadingFilteredConversations = true;

		filterByAgent = agentId;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` +
				new URLSearchParams({
					parent_id: filterByAgent
				}),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);

		const responseBody = await response.json();
		if (response.ok) {
			filteredConversations = responseBody.items;
		} else {
			logger.error('CHATTBL_LIST_TBL', responseBody);
			alert(
				'Failed to fetch filtered conversations: ' +
					(responseBody.message || JSON.stringify(responseBody))
			);
		}

		isLoadingFilteredConversations = false;
	}
</script>

<svelte:head>
	<title>Chat Table</title>
</svelte:head>

<div class="flex flex-col gap-4 h-[calc(100vh-4.25rem)]">
	<div class="flex gap-2 pt-4 pl-6">
		<Button
			variant="ghost"
			class="px-1.5 py-1 h-[unset] text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm {selectedFilter ==
			'agents'
				? 'text-secondary hover:text-secondary border-secondary'
				: 'text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]'}"
			on:click={() => (selectedFilter = 'agents')}
		>
			Agents
		</Button>

		<Button
			variant="ghost"
			class="px-1.5 py-1 h-[unset] text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm {selectedFilter ==
			'all'
				? 'text-secondary hover:text-secondary border-secondary'
				: 'text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]'}"
			on:click={() => (selectedFilter = 'all')}
		>
			All Conversations
		</Button>
	</div>

	{#if selectedFilter == 'agents'}
		<div
			style="grid-template-columns: 2fr 5fr;"
			class="grow grid grid-cols-2 pt-0 h-1 bg-[#FAFBFC] data-dark:bg-[#1E2024] border-t border-[#E5E5E5] data-dark:border-[#484C55]"
		>
			<div
				class="flex flex-col items-center gap-4 px-6 py-3 bg-white data-dark:bg-[#303338] border-r border-[#E5E5E5] data-dark:border-[#484C55] overflow-auto"
			>
				<button
					on:click={() => (isAddingAgent = true)}
					class="flex flex-col items-center justify-center gap-2 h-28 min-h-28 w-full bg-secondary/[0.12] rounded-lg"
				>
					<div class="flex items-center justify-center h-8 bg-secondary rounded-full aspect-square">
						<AddIcon class="h-4 w-4 text-white" />
					</div>

					<span class="font-medium text-sm"> New Agent </span>
				</button>

				{#each $pastChatAgents as chatTable (chatTable.id)}
					<button
						on:click={() => handleFilterByAgent(chatTable.id)}
						title={chatTable.id}
						class="flex flex-col h-28 min-h-28 w-full border border-[#E5E5E5] data-dark:border-[#484C55] rounded-lg"
					>
						<div
							class="grow flex items-start p-3 w-full border-b border-[#E5E5E5] data-dark:border-[#484C55]"
						>
							<div class="flex items-start gap-1.5">
								<div
									class="relative h-[18px] w-[18px] bg-secondary/[0.12] rounded-sm overflow-hidden"
								>
									<ChatAgentIcon
										class="absolute -bottom-[3px] left-1/2 -translate-x-1/2 h-[20px] aspect-square text-secondary"
									/>
								</div>
								<span class="font-medium text-sm text-left break-all line-clamp-2">
									{chatTable.id}
								</span>
							</div>
						</div>

						<div class="flex p-3">
							<span class="text-xs text-[#999] data-dark:text-[#C9C9C9]">
								Updated at: {new Date(chatTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
							</span>
						</div>
					</button>
				{/each}
			</div>

			<div class="flex flex-col gap-2 px-6 py-3 overflow-auto">
				{#if filterByAgent}
					<a
						title={filterByAgent}
						href="/project/{$page.params.project_id}/chat-table/{filterByAgent}"
						class="flex items-center justify-between mb-2 p-4 w-full bg-white data-dark:bg-[#303338] rounded-sm"
					>
						<div class="flex items-center gap-2">
							<div
								class="flex-[0_0_auto] relative h-6 w-6 bg-secondary/[0.12] rounded-sm overflow-hidden"
							>
								<ChatAgentIcon
									class="absolute -bottom-[3px] left-1/2 -translate-x-1/2 h-[26px] aspect-square text-secondary"
								/>
							</div>
							<span class="font-medium line-clamp-1">{filterByAgent}</span>
						</div>

						<Button
							on:click={(e) => {
								e.preventDefault();
								isDeletingTable = filterByAgent;
								filterByAgent = '';
								filteredConversations = [];
							}}
							variant="ghost"
							title="Delete agent"
							class="px-1.5 py-1 h-[unset] text-xs hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] rounded-full"
						>
							<DeleteIcon class="h-6" />
						</Button>
					</a>

					{#if isLoadingFilteredConversations}
						{#each Array(6) as _}
							<Skeleton
								class="flex flex-col items-center justify-center gap-2 h-10 min-h-10 w-full bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
							/>
						{/each}
					{:else}
						{#each filteredConversations as chatTable (chatTable.id)}
							<a
								title={chatTable.id}
								href="/project/{$page.params.project_id}/chat-table/{chatTable.id}"
								class="group flex items-center justify-start gap-2 px-4 py-2 h-10 min-h-10 w-full text-sm hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] rounded-md transition-colors"
							>
								<ChatTableIcon class="flex-[0_0_auto] h-5 text-secondary" />
								<span class="line-clamp-1">{chatTable.id}</span>

								<!-- Right arrow icon -->
								<svg
									width="14"
									height="13"
									viewBox="0 0 10 9"
									fill="none"
									xmlns="http://www.w3.org/2000/svg"
									class="flex-[0_0_auto] ml-auto mr-3 translate-x-0 group-hover:translate-x-3 transition-transform"
								>
									<path
										fill-rule="evenodd"
										clip-rule="evenodd"
										d="M10 4.5C10.0001 4.43378 9.98695 4.36822 9.96146 4.30711C9.93597 4.246 9.89859 4.19056 9.8515 4.14401L5.7985 0.144109C5.70408 0.0509541 5.57653 -0.000879484 5.44389 1.12942e-05C5.31126 0.000902073 5.18441 0.0544443 5.09125 0.148859C4.99809 0.243274 4.94626 0.370827 4.94715 0.503459C4.94804 0.636091 5.00158 0.762936 5.096 0.856091L8.2815 4.00001H0.5C0.367392 4.00001 0.240215 4.05269 0.146447 4.14646C0.0526785 4.24022 0 4.36739 0 4.5C0 4.6326 0.0526785 4.75978 0.146447 4.85354C0.240215 4.94731 0.367392 4.99999 0.5 4.99999H8.2815L5.096 8.14391C5.04925 8.19003 5.01204 8.24492 4.9865 8.30542C4.96096 8.36593 4.94759 8.43087 4.94715 8.49654C4.94671 8.56221 4.95921 8.62733 4.98393 8.68817C5.00866 8.74901 5.04512 8.80439 5.09125 8.85114C5.13738 8.89789 5.19226 8.9351 5.25277 8.96064C5.31327 8.98618 5.37822 8.99955 5.44389 8.99999C5.50957 9.00043 5.57468 8.98793 5.63553 8.96321C5.69637 8.93848 5.75175 8.90202 5.7985 8.85589L9.851 4.85599C9.89818 4.80948 9.93565 4.75406 9.96123 4.69295C9.98681 4.63184 9.99999 4.56625 10 4.5Z"
										fill="currentColor"
									/>
								</svg>
							</a>
						{/each}

						<Button
							variant="outline"
							title="New conversation"
							on:click={() => {
								selectedAgent = filterByAgent;
								isAddingConversation = true;
							}}
							class="flex items-center gap-3 p-4 w-full h-10 min-h-10 max-h-10 text-secondary hover:text-secondary text-center border-2 border-secondary bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-lg whitespace-nowrap overflow-hidden"
						>
							<AddIcon class="w-3 h-3" />
							New conversation
						</Button>
					{/if}
				{:else}
					<span class="self-center my-auto font-medium text-[#999]">
						Select agent to filter conversations
					</span>
				{/if}
			</div>
		</div>
	{:else}
		<div
			style="grid-auto-rows: 112px;"
			class="grow grid grid-cols-2 lg:grid-cols-4 2xl:grid-cols-6 grid-flow-row gap-4 p-6 pt-0 h-1 bg-[#FAFBFC] data-dark:bg-[#1E2024] overflow-auto"
		>
			<button
				on:click={() => {
					selectedAgent = '';
					isAddingConversation = true;
				}}
				class="flex flex-col items-center justify-center gap-2 bg-secondary/[0.12] rounded-lg"
			>
				<div class="flex items-center justify-center h-8 bg-secondary rounded-full aspect-square">
					<AddIcon class="h-4 w-4 text-white" />
				</div>

				<span class="font-medium text-sm"> New Conversation </span>
			</button>

			{#if isLoadingMoreCConv}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
					/>
				{/each}
			{:else}
				{#each $pastChatConversations as chatTable (chatTable.id)}
					<a
						href={`/project/${$page.params.project_id}/chat-table/${chatTable.id}`}
						title={chatTable.id}
						class="flex flex-col border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
					>
						<div
							class="grow flex items-start p-3 border-b border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1.5">
								<ChatTableIcon class="flex-[0_0_auto] h-5 w-5 text-secondary" />
								<span class="font-medium text-sm break-all line-clamp-2">{chatTable.id}</span>
							</div>
						</div>

						<div class="flex items-center justify-between gap-2 p-3">
							<span
								title={new Date(chatTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
								class="text-xs text-[#999] data-dark:text-[#C9C9C9] line-clamp-1"
							>
								Updated at: {new Date(chatTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
							</span>

							{#if chatTable.parent_id}
								<span
									style="background-color: {chatTable.parent_id
										? '#CFE8FF'
										: 'unset'}; color: {chatTable.parent_id ? '#3A73B6' : 'unset'}; "
									class="w-min px-1 py-0.5 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
								>
									{chatTable.parent_id}
								</span>
							{/if}
						</div>
					</a>
				{/each}
			{/if}
		</div>
	{/if}
</div>

<AddAgentDialog bind:isAddingAgent />
<AddConversationDialog bind:isAddingConversation {selectedAgent} bind:filteredConversations />
<DeleteDialogs isDeletingColumn={null} isDeletingRow={null} bind:isDeletingTable />
