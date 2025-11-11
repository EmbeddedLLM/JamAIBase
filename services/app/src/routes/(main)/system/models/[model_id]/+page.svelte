<script lang="ts">
	import { page } from '$app/state';
	import { MODEL_TYPES } from '$lib/constants.js';

	import { CloudDeployments, ModelDetails } from './(components)';
	import { Button } from '$lib/components/ui/button';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';

	let { data } = $props();

	let activeTab = $state<'details' | 'cloud'>('details');
</script>

<svelte:head>
	<title>Model Setup - {page.params.model_id}</title>
</svelte:head>

<div class="grow px-4 pb-6">
	{#await data.modelConfig}
		<div class="flex flex-col gap-4">
			<div class="h-32 w-full animate-pulse rounded-lg bg-white"></div>
			<div class="h-32 w-full animate-pulse rounded-lg bg-white"></div>
			<div class="h-32 w-full animate-pulse rounded-lg bg-white"></div>
			<div class="h-32 w-full animate-pulse rounded-lg bg-white"></div>
		</div>
	{:then modelConfig}
		{#if modelConfig.data}
			<div class=" flex h-full flex-col">
				<!-- Heading  -->
				<div class="flex items-center gap-2">
					<Button
						variant="ghost"
						href={page.state.page ? `/system/models?page=${page.state.page}` : '/system/models'}
						title="Back to model catalogue"
						class="flex aspect-square h-8 items-center justify-center p-0 sm:h-9"
					>
						<ArrowBackIcon class="!h-7 !w-7 text-[#98A2B3]" />
					</Button>

					<h1 class="flex items-center justify-start gap-x-3 text-lg text-[#344054]">
						{modelConfig.data.name}
						<span class="rounded-md bg-[#E9D9FF] px-2 py-0.5 text-xs text-purple-700">
							{MODEL_TYPES[modelConfig.data.type] ?? modelConfig.data.type}
						</span>
					</h1>
				</div>

				<!-- Main Content -->
				<section class="flex flex-1 flex-col overflow-hidden pt-5">
					<div class="flex items-center justify-start gap-x-5">
						<button
							class="relative rounded-t-xl px-4 py-2 text-sm font-medium transition-all duration-200"
							class:bg-white={activeTab === 'details'}
							class:text-[#344054]={activeTab === 'details'}
							class:text-gray-400={activeTab !== 'details'}
							onclick={() => (activeTab = 'details')}
						>
							Model Details
						</button>
						<button
							class="relative rounded-t-xl px-4 py-2 text-sm font-medium transition-all duration-200"
							class:bg-white={activeTab === 'cloud'}
							class:text-[#344054]={activeTab === 'cloud'}
							class:text-gray-400={activeTab !== 'cloud'}
							onclick={() => (activeTab = 'cloud')}
						>
							Cloud Deployments
						</button>

						<!-- <button
              class="relative rounded-t-xl px-4 py-2 text-sm font-medium transition-all duration-200"
              class:bg-white={activeTab === 'benchmark'}
              class:text-[#344054]={activeTab === 'benchmark'}
              class:text-gray-400={activeTab !== 'benchmark'}
              onclick={() => (activeTab = 'benchmark')}
            >
              Benchmarks
            </button> -->
					</div>

					<div
						class="flex h-1 grow flex-col overflow-y-auto rounded-b-xl rounded-tr-xl bg-background"
						class:rounded-tl-xl={activeTab !== 'details'}
					>
						{#if activeTab === 'details'}
							<ModelDetails model={modelConfig.data} />
						{:else if activeTab === 'cloud'}
							<CloudDeployments model={modelConfig.data} />
							<!-- {:else if activeTab === 'benchmark'}
              <Benchmark /> -->
						{/if}
					</div>
				</section>
			</div>
		{/if}
	{/await}
</div>
