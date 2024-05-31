<script lang="ts">
	import { onMount } from 'svelte';
	import throttle from 'lodash/throttle';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { modelsAvailable } from '$globalStore';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';

	export let selectedModel: string;
	export let selectCb: (modelId: string) => void = (modelId) => (selectedModel = modelId);
	export let capabilityFilter: 'completion' | 'chat' | 'image' | 'embed' | 'rerank' | undefined =
		undefined;

	/** Additional trigger button class */
	let className: string | undefined = undefined;
	export { className as class };
	export let sameWidth: boolean = true;
	/** Button disabled control */
	export let disabled: boolean = false;
	/** Text to display on select trigger button */
	export let buttonText: string;

	async function getModels() {
		const response = await fetch(
			'/api/v1/models' +
				(capabilityFilter ? `?${new URLSearchParams({ capabilities: capabilityFilter })}` : ''),
			{
				method: 'GET',
				credentials: 'same-origin'
			}
		);

		const responseBody = await response.json();
		if (response.ok) {
			$modelsAvailable = responseBody.data;
		} else {
			logger.error('MODELS_FETCH_FAILED', responseBody);
			alert('Failed to fetch models: ' + (responseBody.message || JSON.stringify(responseBody)));
		}
	}
	const throttledInvalidateModels = throttle(getModels, 5000);

	onMount(() => {
		getModels();
	});
</script>

<Select.Root>
	<!-- ? Select.Trigger has no event listener props for some reason -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div on:mouseenter={throttledInvalidateModels} on:focusin={throttledInvalidateModels}>
		<Select.Trigger asChild let:builder>
			<Button
				{disabled}
				builders={[builder]}
				variant="outline"
				title="Select model"
				class={cn(
					'flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]',
					className
				)}
			>
				<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
					{buttonText}
				</span>

				<ChevronDown class="h-4 w-4" />
			</Button>
		</Select.Trigger>
	</div>
	<Select.Content {sameWidth} side="bottom" class="max-h-96 overflow-y-auto">
		{#each $modelsAvailable as { id, languages }}
			<Select.Item
				on:click={() => selectCb(id)}
				value={id}
				label={id}
				class="flex justify-between gap-10 cursor-pointer"
			>
				{id}
				<span class="uppercase">{languages.join(', ')}</span>
			</Select.Item>
		{/each}
		{#if $modelsAvailable.length == 0}
			<span class="m-6 min-w-max text-sm text-left text-foreground-content/60 pointer-events-none">
				No models available
			</span>
		{/if}
	</Select.Content>
</Select.Root>
