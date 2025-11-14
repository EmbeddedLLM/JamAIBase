<script lang="ts">
	import { cn } from '$lib/utils';
	import type { PriceRes } from '$lib/types';

	import * as Select from '$lib/components/ui/select';

	let {
		prices,
		selectedOrgPlan = $bindable(),
		class: className = undefined
	}: {
		prices: PriceRes[];
		selectedOrgPlan: PriceRes | null;
		/** Additional trigger button class */
		class?: string | undefined;
	} = $props();
</script>

<Select.Root
	type="single"
	bind:value={() => selectedOrgPlan?.id ?? '',
	(v) => (selectedOrgPlan = prices.find((p) => p.id === v) ?? null)}
>
	<Select.Trigger
		data-testid="org-plan-select-btn"
		title="Select plan"
		class={cn(
			'mb-1 flex h-10 min-w-full items-center justify-between gap-8 border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] data-dark:bg-[#42464e]',
			className
		)}
	>
		{#snippet children()}
			<span class="line-clamp-1 whitespace-nowrap text-left font-normal capitalize">
				{selectedOrgPlan
					? `${selectedOrgPlan.name} - $${selectedOrgPlan.flat_cost}/month`
					: 'Select plan'}
			</span>
		{/snippet}
	</Select.Trigger>
	<Select.Content data-testid="org-plan-select-list" class="max-h-64 overflow-y-auto">
		{#each prices as price}
			<Select.Item
				value={price.id}
				label={`${price.name} - $${price.flat_cost}/month`}
				class="flex cursor-pointer justify-between gap-10"
			>
				{`${price.name} - $${price.flat_cost}/month`}
			</Select.Item>
		{/each}
	</Select.Content>
</Select.Root>
