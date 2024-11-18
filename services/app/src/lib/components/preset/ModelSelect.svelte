<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import throttle from 'lodash/throttle';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { modelsAvailable } from '$globalStore';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import Portal from '$lib/components/Portal.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';

	export let selectedModel: string;
	export let selectCb: (modelId: string) => void = (modelId) => (selectedModel = modelId);
	export let capabilityFilter: 'completion' | 'chat' | 'image' | 'embed' | 'rerank' | undefined =
		undefined;
	export let showCapabilities = false;

	/** Additional trigger button class */
	let className: string | undefined = undefined;
	export { className as class };
	export let sameWidth: boolean = true;
	/** Button disabled control */
	export let disabled: boolean = false;
	/** Text to display on select trigger button */
	export let buttonText: string;

	async function getModels() {
		if (disabled) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/models`, {
			credentials: 'same-origin',
			headers: {
				'x-project-id': $page.params.project_id
			}
		});

		const responseBody = await response.json();
		if (response.ok) {
			$modelsAvailable = responseBody.data;
		} else {
			logger.error('MODELS_FETCH_FAILED', responseBody);
			console.error(responseBody);
			toast.error('Failed to fetch models', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}
	const throttledInvalidateModels = throttle(getModels, 5000);

	let animationFrameId: ReturnType<typeof requestAnimationFrame> | null;
	let tooltip: HTMLDivElement;
	let tooltipPos = { x: 0, y: 0, visible: false };
	function handleMouseOver(event: MouseEvent) {
		if (animationFrameId) {
			cancelAnimationFrame(animationFrameId);
		}

		animationFrameId = requestAnimationFrame(() => {
			let x = event.clientX;
			let y = event.clientY;

			if (window.innerWidth - event.clientX - 15 < tooltip.offsetWidth) {
				x -= tooltip.offsetWidth;
			} else {
				x += 10;
				y += 10;
			}

			if (window.innerHeight - event.clientY < tooltip.offsetHeight) {
				y -= tooltip.offsetHeight;
			}

			tooltipPos = { x, y, visible: true };

			animationFrameId = null;
		});
	}
</script>

<Select.Root
	selected={{ value: selectedModel }}
	onSelectedChange={(v) => {
		v && selectCb(v.value);
	}}
>
	<!-- ? Select.Trigger has no event listener props for some reason -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div on:mouseenter={throttledInvalidateModels} on:focusin={throttledInvalidateModels}>
		<Select.Trigger asChild let:builder>
			<Button
				{disabled}
				builders={[builder]}
				variant="outline-neutral"
				title={buttonText}
				class={cn(
					selectedModel ? '' : 'italic text-muted-foreground hover:text-muted-foreground',
					'grid grid-cols-[minmax(0,1fr)_min-content] gap-2 pl-3 pr-2 h-10 min-w-full rounded-md',
					className
				)}
			>
				<span class="w-full whitespace-nowrap line-clamp-1 font-normal text-left">
					{buttonText}
				</span>

				<ChevronDown class="flex-[0_0_auto] h-4 w-4" />
			</Button>
		</Select.Trigger>
	</div>
	<Select.Content {sameWidth} side="bottom" class="max-h-64 overflow-y-auto">
		{#each $modelsAvailable as { id, name, languages, capabilities, owned_by }}
			{@const isDisabled =
				owned_by !== 'ellm' &&
				$page.data.organizationData?.tier === 'free' &&
				!$page.data.organizationData?.credit &&
				!$page.data.organizationData?.external_keys?.[owned_by]}
			{#if !capabilityFilter || capabilities.includes(capabilityFilter)}
				<Select.Item
					disabled={isDisabled}
					title={!isDisabled ? id : undefined}
					value={id}
					label={id}
					labelSelected
					class="relative grid grid-cols-[minmax(0,1fr)_45px] gap-2 cursor-pointer"
				>
					{#if isDisabled}
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<!-- svelte-ignore a11y-mouse-events-have-key-events -->
						<div
							on:mousemove={handleMouseOver}
							on:mouseleave={() => {
								if (animationFrameId) cancelAnimationFrame(animationFrameId);
								tooltipPos.visible = false;
							}}
							class="absolute -top-1 -bottom-1 left-0 right-0 pointer-events-auto cursor-default"
						></div>
					{/if}
					{name}

					{#if showCapabilities}
						<span class="ml-auto uppercase place-self-center text-xs text-right">
							{capabilities.join('\n')}
						</span>
					{:else}
						<span class="ml-auto uppercase place-self-center">{languages.join(', ')}</span>
					{/if}
				</Select.Item>
			{/if}
		{/each}
		{#if $modelsAvailable.length == 0}
			<span class="m-6 min-w-max text-sm text-left text-foreground-content/60 pointer-events-none">
				No models available
			</span>
		{/if}
	</Select.Content>
</Select.Root>

<Portal>
	<Tooltip
		bind:tooltip
		class="z-[9999]"
		style="--arrow-size: 10px; left: {tooltipPos.x}px; top: {tooltipPos.y}px; visibility: {tooltipPos.visible
			? 'visible'
			: 'hidden'}"
		showArrow={false}
	>
		Upgrade your plan, purchase credits, or provide an API key to use this model
	</Tooltip>
</Portal>
