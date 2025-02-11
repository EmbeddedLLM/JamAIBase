<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { page } from '$app/stores';
	import { modelsAvailable } from '$globalStore';
	import { pastChatAgents } from '$lib/components/tables/tablesStore';
	import { jamaiApiVersion, tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	export let isAddingAgent: boolean;

	let isLoading = false;
	let agentName = '';
	let selectedModel = '';

	async function handleAddAgent() {
		if (!agentName) return toast.error('Agent ID is required', { id: 'agent-id-req' });
		if (!selectedModel) return toast.error('Model not selected', { id: 'model-not-selected' });

		if (!tableIDPattern.test(agentName))
			return toast.error(
				'Agent ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'agent-id-invalid' }
			);

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				id: agentName,
				version: jamaiApiVersion,
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
							object: 'gen_config.llm',
							model: selectedModel,
							multi_turn: true
						} satisfies GenTableCol['gen_config']
					}
				]
			})
		});

		const responseBody = await response.json();
		if (!response.ok) {
			logger.error('CHATTBL_AGENT_ADD', responseBody);
			toast.error('Failed to add agent', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		} else {
			$pastChatAgents = [responseBody, ...$pastChatAgents];

			isAddingAgent = false;
			agentName = '';
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={isAddingAgent}>
	<Dialog.Content
		data-testid="new-agent-dialog"
		class="h-[80vh] max-h-fit w-[clamp(0px,30rem,100%)]"
	>
		<Dialog.Header>New agent</Dialog.Header>

		<div class="grow flex flex-col gap-3 py-3 w-full overflow-auto">
			<div class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center">
				<label for="agent-id" class="font-medium text-left text-xs sm:text-sm text-black">
					Agent ID*
				</label>

				<InputText bind:value={agentName} name="agent-id" placeholder="Required" />
			</div>

			<div class="flex flex-col gap-1 px-4 sm:px-6">
				<span class="font-medium text-left text-xs sm:text-sm text-black"> Models* </span>

				<ModelSelect
					capabilityFilter="chat"
					sameWidth={true}
					bind:selectedModel
					buttonText={($modelsAvailable.find((model) => model.id == selectedModel)?.name ??
						selectedModel) ||
						'Select model'}
					class="{!selectedModel
						? 'italic text-muted-foreground'
						: ''} bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent"
				/>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleAddAgent}
					type="button"
					disabled={isLoading}
					loading={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
