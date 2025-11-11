<script lang="ts">
	import type { ModelDeployment } from '$lib/types';
	import type { LayoutData } from '../$types';

	import DeleteDeploymentDialog from './DeleteDeploymentDialog.svelte';
	import ManageDeploymentDialog from './ManageDeploymentDialog.svelte';
	import * as Table from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	let { data }: { data: LayoutData } = $props();

	let isEditDeploymentOpen = $state(false);
	let selectedEditDeploymentId = $state<string>();

	let isDeleteDeploymentOpen = $state(false);
	let selectedDeleteDeployment = $state<ModelDeployment>();
</script>

<section class="flex max-w-full flex-col gap-2">
	<h3 class="flex items-center space-x-2">
		<span>Cloud Deployment Management</span>
	</h3>

	<div
		class="mt-0 h-[36rem] max-h-[36rem] flex-col overflow-hidden rounded-xl bg-background data-[state=active]:flex"
	>
		<div class="flex h-full min-h-0 flex-col overflow-auto [&>div]:h-1 [&>div]:grow">
			<Table.Root class="w-full">
				<Table.Header>
					<Table.Row class="sticky top-0 bg-background hover:bg-background">
						<Table.Head class="min-w-48">Endpoint Name</Table.Head>
						<Table.Head class="min-w-48">Model</Table.Head>
						<Table.Head class="min-w-40">Model ID</Table.Head>
						<Table.Head class="min-w-32">API Base</Table.Head>
						<Table.Head>Actions</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#await data.deployments}
						{#each Array(4) as _}
							<Table.Row>
								<Table.Cell colspan={100} class="p-1.5">
									<Skeleton class="h-10 w-full" />
								</Table.Cell>
							</Table.Row>
						{/each}
					{:then deployments}
						{#if deployments.data}
							{#if deployments.data.length > 0}
								{#each deployments.data as deployment}
									<Table.Row>
										<Table.Cell class="font-medium">{deployment.name}</Table.Cell>
										<Table.Cell>{deployment.model?.name}</Table.Cell>
										<Table.Cell>{deployment.model_id}</Table.Cell>

										<Table.Cell class="text-blue-500 underline">{deployment.api_base}</Table.Cell>
										<Table.Cell>
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
													size="sm"
													variant="destructive"
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

								<!-- {#if deployments.isFetching}
								<Table.Row>
									<Table.Cell colspan={1000}>
										<LoadingSpinner class="mx-auto my-6" />
									</Table.Cell>
								</Table.Row>
							{/if} -->
							{:else}
								<Table.Row>
									<Table.Cell colspan={999}>
										<div class="left-1/2 flex h-64 items-center justify-center">
											<div class="flex flex-col gap-1 text-center text-gray-500">
												<span class="text-base font-medium">No cloud deployments found</span>
												<span class="text-sm">Deploy a model to see it listed here</span>
											</div>
										</div>
									</Table.Cell>
								</Table.Row>
							{/if}
						{:else}
							<div class="sticky left-1/2 flex h-64 -translate-x-1/2 items-center justify-center">
								<div class="absolute flex w-80 flex-col gap-1 text-center text-gray-500">
									<span class="text-base font-medium">Error loading deployments</span>
									<span class="text-sm">
										{deployments?.error.message || JSON.stringify(deployments?.error)}
									</span>
								</div>
							</div>
						{/if}
					{/await}
				</Table.Body>
			</Table.Root>
		</div>
	</div>

	{#if selectedEditDeploymentId}
		<ManageDeploymentDialog
			bind:open={isEditDeploymentOpen}
			deploymentId={selectedEditDeploymentId}
		/>
	{/if}
	<DeleteDeploymentDialog
		bind:open={isDeleteDeploymentOpen}
		deployment={selectedDeleteDeployment}
	/>
</section>
