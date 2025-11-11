<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import logger from '$lib/logger';
	import type { ModelDeployment } from '$lib/types';

	import DeploymentDetails from './DeploymentDetails.svelte';
	import * as Dialog from '$lib/components/ui/dialog';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	let { open = $bindable(), deploymentId }: { open: boolean; deploymentId: string } = $props();

	let activeTab = $state<'details' | 'logs'>('details');

	const getDeployment = async (
		id: string
	): Promise<{
		data: ModelDeployment | null;
		error?: any;
		status?: number;
		refetch: () => void;
	}> => {
		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/models/deployments?${new URLSearchParams([['deployment_id', id]])}`
		);
		const responseBody = await response.json();

		if (!response.ok) {
			logger.error('DEPLOYMENT_GET_ERROR', responseBody);
			return {
				data: null,
				error: responseBody,
				status: response.status,
				refetch: () => (deployment = getDeployment(id))
			};
		}

		return {
			data: responseBody as ModelDeployment,
			refetch: () => (deployment = getDeployment(id))
		};
	};

	let deployment = $derived(getDeployment(deploymentId));
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="w-[clamp(50rem,60vw,80%)] bg-gray-100 md:h-[90vh] lg:h-[80vh]">
		<Dialog.Header class="bg-gray-100">
			<div class="flex flex-col gap-1.5">
				<p class="text-sm text-gray-500">Model Deployment</p>
				<Dialog.Title class="text-base font-medium">
					{#await deployment}
						<p class="text-sm font-normal text-gray-600">Loading...</p>
					{:then deployment}
						{deployment.data?.name}
					{/await}
				</Dialog.Title>
			</div>
		</Dialog.Header>

		<section class="flex flex-1 flex-col overflow-hidden p-4">
			<div class="flex items-center justify-start gap-x-5">
				<button
					class="relative rounded-t-lg p-2 text-sm transition-all duration-200"
					class:bg-white={activeTab === 'details'}
					class:text-[#344054]={activeTab === 'details'}
					class:text-gray-400={activeTab !== 'details'}
					onclick={() => (activeTab = 'details')}
				>
					Deployment Details
				</button>
			</div>

			<!-- tab content  -->
			{#await deployment}
				<div
					class="flex flex-1 flex-col items-center justify-center rounded-b-lg rounded-tr-lg bg-background"
					class:rounded-tl-lg={activeTab !== 'details'}
				>
					<LoadingSpinner class="mx-auto my-6" />
				</div>
			{:then deployment}
				{#if deployment.data}
					<div
						class="flex flex-1 flex-col overflow-y-auto rounded-b-lg rounded-tr-lg bg-background"
						class:rounded-tl-lg={activeTab !== 'details'}
					>
						{#if activeTab === 'details'}
							<DeploymentDetails {deployment} />
						{/if}
					</div>
				{:else}
					<div
						class="flex flex-1 flex-col items-center justify-center rounded-b-lg rounded-tr-lg bg-background p-6"
						class:rounded-tl-lg={activeTab !== 'details'}
					>
						<div class="text-center text-gray-500">
							<span class="text-base font-medium">Error loading deployment</span>
							<p class="mt-2 text-sm">
								{deployment?.error?.message || JSON.stringify(deployment.error)}
							</p>
						</div>
					</div>
				{/if}
			{/await}
		</section>
	</Dialog.Content>
</Dialog.Root>
