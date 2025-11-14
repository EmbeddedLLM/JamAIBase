<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/state';
	import { modelsAvailable } from '$globalStore';
	import { pastChatAgents } from '$lib/components/tables/tablesState.svelte';
	import { jamaiApiVersion, tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	interface Props {
		isAddingAgent: boolean;
	}

	let { isAddingAgent = $bindable() }: Props = $props();

	let isLoading = $state(false);
	let agentName = $state('');
	let selectedModel = $state('');

	async function handleAddAgent() {
		if (!agentName) return toast.error('Agent ID is required', { id: 'agent-id-req' });
		if (!selectedModel) return toast.error('Model not selected', { id: 'model-not-selected' });

		if (!tableIDPattern.test(agentName))
			return toast.error(
				'Agent ID must have at least 1 character and up to 46 characters, start with an alphabet or number, and end with an alphabet or number or these symbols: .?!()-. Characters in the middle can include space and these symbols: .?!@#$%^&*_()-.',
				{ id: 'agent-id-invalid' }
			);

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id
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
	<Dialog.Content data-testid="new-agent-dialog" class="max-h-fit w-[clamp(0px,30rem,100%)]">
		<Dialog.Header>New agent</Dialog.Header>

		<div class="flex w-full grow flex-col gap-3 overflow-auto py-3">
			<div class="flex w-full flex-col space-y-1 px-4 sm:px-6">
				<Label required for="agent-id" class="text-xs sm:text-sm">Agent ID</Label>

				<InputText bind:value={agentName} id="agent-id" name="agent-id" placeholder="Required" />
			</div>

			<div class="flex flex-col space-y-1 px-4 sm:px-6">
				<Label required class="text-xs sm:text-sm">Model</Label>

				<ModelSelect
					capabilityFilter="chat"
					bind:selectedModel
					class="{!selectedModel
						? 'italic text-muted-foreground'
						: ''} border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
				/>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					onclick={handleAddAgent}
					type="button"
					disabled={isLoading}
					loading={isLoading}
					class="relative grow px-6"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
