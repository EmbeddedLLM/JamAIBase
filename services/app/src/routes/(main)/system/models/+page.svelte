<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { AddModelConfigDialog, DeploymentManagement, ModelCatalogue } from './(components)';

	let { data } = $props();

	let isAddingModelConfig = $state(false);

	onMount(() => {
		if (page.url.searchParams.get('onboarding') === 'model_config') {
			isAddingModelConfig = true;
		}
	});
</script>

<svelte:head>
	<title>Model Setup</title>
</svelte:head>

<div class="flex flex-col gap-8 overflow-auto px-6 pb-6">
	<ModelCatalogue bind:isAddingModelConfig {data} />

	<DeploymentManagement {data} />
</div>

<AddModelConfigDialog bind:open={isAddingModelConfig} {data} />

<Dialog.Root
	open={page.url.searchParams.get('onboarding') === 'true'}
	onOpenChange={(v) => {
		if (!v) {
			page.url.searchParams.delete('onboarding');
			goto(`?${page.url.searchParams}`, { invalidate: [] });
		}
	}}
>
	<Dialog.Content class="items-center gap-8 bg-[#F2F4F7] py-24">
		<h2 class="text-2xl font-medium text-[#344054]">Start deploying your first model</h2>
		<Button
			size="sm"
			onclick={() => {
				page.url.searchParams.set('onboarding', 'model_config');
				goto(`?${page.url.searchParams}`, { invalidate: [] });
				isAddingModelConfig = true;
			}}
			class="w-max rounded-full px-6"
		>
			Start
		</Button>
	</Dialog.Content>
</Dialog.Root>
