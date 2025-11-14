<script lang="ts">
	import * as Table from '$lib/components/ui/table';
	import Button from '$lib/components/ui/button/button.svelte';
	import type { ModelConfig } from '$lib/types';
	import {
		AddDeploymentDialog,
		DeleteDeploymentDialog,
		ManageDeploymentDialog
	} from '../../(components)';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import { PROVIDERS } from '$lib/constants';

	let { model }: { model: ModelConfig } = $props();

	let isEditDeploymentOpen = $state(false);
	let selectedEditDeploymentId = $state<string>();

	let isDeleteDeploymentOpen = $state(false);
	let selectedDeleteDeployment = $state<(typeof model.deployments)[number]>();

	let deployOpen = $state<{ open: boolean; value: ModelConfig | null }>({
		open: false,
		value: null
	});
</script>

<Table.Root class="w-full">
	<Table.Header>
		<Table.Row class="sticky top-0 bg-background hover:bg-background">
			<Table.Head class="min-w-48">Endpoint Name</Table.Head>
			<Table.Head class="min-w-32">API Base</Table.Head>
			<Table.Head class="min-w-32">Provider</Table.Head>
			<Table.Head class="min-w-48">Routing ID</Table.Head>
			<Table.Head>Actions</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row class="border-b-0 hover:bg-background">
			<Table.Cell class="px-3 py-2" colspan={5}>
				<button
					onclick={(e) => {
						deployOpen = { open: true, value: model };
					}}
					class="flex h-full w-full items-center gap-1.5 rounded-xl bg-gray-100 px-4 py-3 text-start text-gray-500 duration-300 hover:bg-gray-200/80"
				>
					<AddIcon class="h-2.5" />
					Add Deployment
				</button>
			</Table.Cell>
		</Table.Row>
		{#if model.deployments?.length}
			{@const cloudDeployments = model.deployments.flat()}
			{#if cloudDeployments.length > 0}
				{#each cloudDeployments as deployment}
					<Table.Row class="!border-b">
						<Table.Cell class="py-2 font-medium">{deployment.name}</Table.Cell>
						<Table.Cell class="py-2 text-blue-500 underline">{deployment.api_base}</Table.Cell>
						<Table.Cell class="py-2 font-medium">
							{PROVIDERS[deployment.provider] || deployment.provider}
						</Table.Cell>
						<Table.Cell class="py-2 font-medium">{deployment.routing_id}</Table.Cell>
						<Table.Cell class="py-2">
							<div class="flex gap-2">
								<Button
									tvTheme
									size="sm"
									onclick={() => {
										selectedEditDeploymentId = deployment.id;
										isEditDeploymentOpen = true;
									}}
								>
									Manage
								</Button>
								<Button
									variant="destructive"
									size="sm"
									onclick={() => {
										selectedDeleteDeployment = deployment;
										isDeleteDeploymentOpen = true;
									}}
								>
									Delete
								</Button>
							</div>
						</Table.Cell>
					</Table.Row>
				{/each}
			{:else}
				<Table.Row>
					<Table.Cell colspan={4} class="text-center text-gray-500">
						No cloud deployments found
					</Table.Cell>
				</Table.Row>{/if}
		{/if}
	</Table.Body>
</Table.Root>

<AddDeploymentDialog bind:open={deployOpen} />

{#if selectedEditDeploymentId}
	<ManageDeploymentDialog
		bind:open={isEditDeploymentOpen}
		deploymentId={selectedEditDeploymentId}
	/>
{/if}
<DeleteDeploymentDialog bind:open={isDeleteDeploymentOpen} deployment={selectedDeleteDeployment} />
