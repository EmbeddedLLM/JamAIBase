<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import throttle from 'lodash/throttle';
	import { page } from '$app/state';
	import { activeOrganization, modelsAvailable } from '$globalStore';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';
	import type { ModelConfig } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import Portal from '$lib/components/Portal.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import * as Select from '$lib/components/ui/select';

	interface Props {
		selectedModel: string;
		allowDeselect?: boolean;
		selectCb?: (modelId: string) => void;
		capabilityFilter?: 'completion' | 'chat' | 'image' | 'embed' | 'rerank' | undefined;
		showCapabilities?: boolean;
		/** Additional trigger button class */
		class?: string | undefined;
		/** Button disabled control */
		disabled?: boolean;
	}

	let {
		selectedModel = $bindable(),
		allowDeselect = false,
		selectCb = (modelId) => (selectedModel = modelId),
		capabilityFilter = undefined,
		showCapabilities = false,
		class: className = undefined,
		disabled = false
	}: Props = $props();

	let models = $state<ModelConfig[]>([]);
	let buttonText = $derived(
		(models.find((model) => model.id == selectedModel)?.name ?? selectedModel) ||
			($modelsAvailable.find((model) => model.id == selectedModel)?.name ?? selectedModel) ||
			'Select model'
	);

	async function getModels() {
		if (disabled) return;
		if (!$activeOrganization) return;

		const searchParams = new URLSearchParams([
			['organization_id', $activeOrganization.id],
			['order_by', 'name']
		]);
		if (capabilityFilter) {
			searchParams.append('capabilities', capabilityFilter);
		}

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/organizations/models/catalogue?${searchParams}`,
			{
				credentials: 'same-origin',
				headers: {
					'x-project-id': page.params.project_id
				}
			}
		);

		const responseBody = await response.json();
		if (response.ok) {
			models = responseBody.items;
		} else {
			logger.error('MODELS_FETCH_FAILED', responseBody);
			console.error(responseBody);
			toast.error('Failed to fetch models', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}
	const throttledInvalidateModels = throttle(getModels, 5000);

	onMount(() => {
		if ($activeOrganization && page.params.project_id) {
			fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/organizations/models/catalogue?${new URLSearchParams([['organization_id', $activeOrganization.id]])}`,
				{
					credentials: 'same-origin',
					headers: {
						'x-project-id': page.params.project_id
					}
				}
			)
				.then((res) => Promise.all([res, res.json()]))
				.then(([response, responseBody]) => {
					if (response.ok) {
						models = responseBody.items;
					} else {
						logger.error('MODELS_FETCH_FAILED', responseBody);
						console.error(responseBody);
					}
				});
		}
	});

	let animationFrameId: ReturnType<typeof requestAnimationFrame> | null = $state(null);
	let tooltip: HTMLDivElement | undefined = $state();
	let tooltipPos = $state({ x: 0, y: 0, visible: false });
	function handleMouseOver(event: MouseEvent) {
		if (animationFrameId) {
			cancelAnimationFrame(animationFrameId);
		}

		animationFrameId = requestAnimationFrame(() => {
			if (!tooltip) return;
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
	{disabled}
	type="single"
	{allowDeselect}
	bind:value={selectedModel}
	onValueChange={selectCb}
>
	<!-- ? Select.Trigger has no event listener props for some reason -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<Select.Trigger
		onmouseenter={throttledInvalidateModels}
		onfocusin={throttledInvalidateModels}
		title={buttonText}
		class={cn(
			selectedModel ? '' : 'italic text-muted-foreground hover:text-muted-foreground',
			'grid h-10 min-w-full grid-cols-[minmax(0,1fr)_min-content] gap-2 pl-3 pr-2',
			className
		)}
	>
		<span class="line-clamp-1 w-full whitespace-nowrap text-left font-normal">
			{buttonText}
		</span>
	</Select.Trigger>
	<Select.Content data-testid="model-select-list" side="bottom" class="max-h-64 overflow-y-auto">
		{#each models as { id, name, languages, capabilities, owned_by }}
			<!-- TODO: simplify this -->
			{@const isDisabled =
				(owned_by !== 'ellm' &&
					owned_by !== 'custom' &&
					page.data.organizationData &&
					page.data.organizationData.credit === 0 &&
					page.data.organizationData.credit_grant === 0 &&
					!page.data.organizationData.external_keys?.[owned_by ?? '']) ||
				(page.data.organizationData?.price_plan_id === 'base' &&
					page.data.organizationData.credit === 0 &&
					page.data.organizationData.credit_grant === 0 &&
					page.data.organizationData?.quotas?.reranker_searches?.quota === 0 &&
					capabilities.every((c) => c === 'rerank'))}
			{#if !capabilityFilter || capabilities.includes(capabilityFilter)}
				<Select.Item
					disabled={isDisabled}
					title={!isDisabled ? id : undefined}
					value={id}
					label={id}
					class="relative grid cursor-pointer grid-cols-[minmax(0,1fr)_45px] gap-2"
				>
					{#if isDisabled}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<!-- svelte-ignore a11y_mouse_events_have_key_events -->
						<div
							onmousemove={handleMouseOver}
							onmouseleave={() => {
								if (animationFrameId) cancelAnimationFrame(animationFrameId);
								tooltipPos.visible = false;
							}}
							class="pointer-events-auto absolute -bottom-1 -top-1 left-0 right-0 cursor-default"
						></div>

						<svg
							viewBox="0 0 18 18"
							fill="none"
							xmlns="http://www.w3.org/2000/svg"
							class="absolute left-1 h-6 w-6"
						>
							<path
								d="M11.8 7.8457H6.2C5.8134 7.8457 5.5 8.1901 5.5 8.61493V13.2303C5.5 13.6552 5.8134 13.9995 6.2 13.9995H11.8C12.1866 13.9995 12.5 13.6552 12.5 13.2303V8.61493C12.5 8.1901 12.1866 7.8457 11.8 7.8457Z"
								stroke="#98A2B3"
								stroke-linecap="round"
								stroke-linejoin="round"
							/>
							<path
								d="M11.4508 7.84615V6.69231C11.4508 5.97826 11.1927 5.29346 10.7332 4.78856C10.2737 4.28365 9.65056 4 9.00078 4C8.351 4 7.72783 4.28365 7.26837 4.78856C6.80891 5.29346 6.55078 5.97826 6.55078 6.69231V7.84615"
								stroke="#98A2B3"
								stroke-linecap="round"
								stroke-linejoin="round"
							/>
							<path
								d="M8.99844 11.3073C9.19174 11.3073 9.34844 11.1351 9.34844 10.9227C9.34844 10.7103 9.19174 10.5381 8.99844 10.5381C8.80514 10.5381 8.64844 10.7103 8.64844 10.9227C8.64844 11.1351 8.80514 11.3073 8.99844 11.3073Z"
								stroke="#98A2B3"
								stroke-linecap="round"
								stroke-linejoin="round"
							/>
						</svg>
					{/if}
					{name}

					{#if showCapabilities}
						<span class="ml-auto place-self-center text-right text-xs uppercase">
							{capabilities.join('\n')}
						</span>
					{:else}
						<div class="ml-auto grid grid-cols-2 gap-0.5 uppercase">
							{#each languages as language, index}
								<span>
									{languages.length - 1 !== index ? `${language},` : language}
								</span>
							{/each}
						</div>
					{/if}
				</Select.Item>
			{/if}
		{/each}
		{#if models.length == 0}
			<span class="text-foreground-content/60 pointer-events-none m-6 min-w-max text-left text-sm">
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
