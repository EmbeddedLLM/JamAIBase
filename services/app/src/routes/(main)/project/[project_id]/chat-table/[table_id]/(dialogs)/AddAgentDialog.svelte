<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { invalidate } from '$app/navigation';
	import { modelsAvailable } from '$globalStore';
	import logger from '$lib/logger';
	import type { ChatRequest } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import Range from '$lib/components/Range.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { pastChatAgents } from '../../chatTablesStore';

	const { PUBLIC_JAMAI_URL } = env;

	export let isAddingAgent: boolean;

	let isLoading = false;
	let agentName = '';
	let selectedModel = '';
	let temperature = '1';
	let maxTokens = '1000';
	let topP = '0.1';
	let systemPrompt = '';
	let userOpener = '';
	let aiOpener = '';

	async function handleAddAgent() {
		if (!agentName) {
			return alert('Please fill in all fields');
		}

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				id: agentName,
				cols: [
					{
						id: 'User',
						dtype: 'str',
						vlen: 0,
						gen_config: null
					},
					{
						id: 'AI',
						dtype: 'str',
						vlen: 0,
						gen_config: {
							model: selectedModel,
							messages: [
								{
									role: 'system',
									content: systemPrompt
								}
							],
							temperature: parseFloat(temperature),
							max_tokens: parseInt(maxTokens),
							top_p: parseFloat(topP)
						} satisfies Partial<ChatRequest>
					}
				]
			})
		});

		const responseBody = await response.json();
		if (!response.ok) {
			logger.error('CHATTBL_AGENT_ADD', responseBody);
			alert('Failed to add agent: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			if (userOpener || aiOpener) {
				const openerResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/rows/add`, {
					method: 'POST',
					headers: {
						Accept: 'text/event-stream',
						'Content-Type': 'application/json'
					},
					body: JSON.stringify({
						table_id: responseBody.id,
						data: [
							{
								User: userOpener,
								AI: aiOpener
							}
						],
						stream: false
					})
				});

				if (!openerResponse.ok) {
					const openerResponseBody = await openerResponse.json();
					logger.error('CHATTBL_AGENT_ADDOPENER', openerResponseBody);
					alert(
						'Failed to add conversation opener: ' +
							(responseBody.message || JSON.stringify(responseBody))
					);
				}
			}

			$pastChatAgents = [
				{
					id: agentName,
					cols: [],
					lock_till: 0,
					updated_at: new Date().toISOString(),
					indexed_at_fts: null,
					indexed_at_sca: null,
					indexed_at_vec: null,
					parent_id: null,
					title: ''
				},
				...$pastChatAgents
			];

			isAddingAgent = false;
			agentName = '';
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={isAddingAgent}>
	<Dialog.Content style="min-width: 65rem; height: 90vh;">
		<Dialog.Header>New agent</Dialog.Header>

		<div class="grow py-3 w-full overflow-auto">
			<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Agent ID
				</span>

				<input
					type="text"
					bind:value={agentName}
					class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<div class="flex flex-col gap-1 px-6 pl-8 py-2">
				<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Models
				</span>

				<ModelSelect
					capabilityFilter="chat"
					sameWidth={true}
					bind:selectedModel
					buttonText={selectedModel || 'Select model'}
				/>
			</div>

			<div class="grid grid-cols-3 gap-4 px-6 pl-8 py-2 w-full text-center">
				<div class="flex flex-col gap-1">
					<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Temperature
					</span>

					<input
						type="number"
						step=".01"
						bind:value={temperature}
						on:blur={() =>
							(temperature =
								parseFloat(temperature) <= 0 ? '0.01' : parseFloat(temperature).toFixed(2))}
						class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>

					<Range bind:value={temperature} min=".01" max="1" step=".01" />
				</div>

				<div class="flex flex-col gap-1">
					<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Max tokens
					</span>

					<input
						type="number"
						bind:value={maxTokens}
						on:blur={() =>
							(maxTokens = parseInt(maxTokens) <= 0 ? '1' : parseInt(maxTokens).toString())}
						class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>

					<Range
						bind:value={maxTokens}
						min="1"
						max={$modelsAvailable.find((model) => model.id == selectedModel)?.contextLength ?? 0}
						step="1"
					/>
				</div>

				<div class="flex flex-col gap-1">
					<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Top-p
					</span>

					<input
						type="number"
						step=".001"
						bind:value={topP}
						on:blur={() => (topP = parseFloat(topP) <= 0 ? '0.001' : parseFloat(topP).toFixed(3))}
						class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>

					<Range bind:value={topP} min=".001" max="1" step=".001" />
				</div>
			</div>

			<div class="grid grid-rows-[min-content_1fr] px-6 pl-8 py-4 overflow-auto">
				<span class="font-medium text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Customize system prompt
				</span>

				<textarea
					bind:value={systemPrompt}
					id="system-prompt"
					placeholder="Enter system prompt"
					class="mt-4 p-2 h-64 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<!-- <span class="mt-6 px-8 font-medium">Conversation opener</span> -->

			<div class="grid grid-cols-2 px-6">
				<div class="grid grid-rows-[min-content_1fr] px-2 py-4 overflow-auto">
					<span class="font-medium text-sm text-[#999] data-dark:text-[#C9C9C9]">
						User message
					</span>

					<textarea
						bind:value={userOpener}
						id="user-message"
						placeholder="Enter user message"
						class="mt-4 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>
				</div>

				<div class="grid grid-rows-[min-content_1fr] px-2 pr-0 py-4 overflow-auto">
					<span class="font-medium text-sm text-[#999] data-dark:text-[#C9C9C9]">
						AI response
					</span>

					<textarea
						bind:value={aiOpener}
						id="ai-response"
						placeholder="Enter AI response"
						class="mt-4 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>
				</div>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isAddingAgent = false)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					on:click={handleAddAgent}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
