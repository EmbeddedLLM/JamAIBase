<script lang="ts">
	import { page } from '$app/stores';
	import capitalize from 'lodash/capitalize';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { cn } from '$lib/utils';

	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';

	export let selectedOrgPlan: string;
	export let selectCb: (planId: string) => void;

	/** Additional trigger button class */
	let className: string | undefined = undefined;
	export { className as class };
</script>

<Select.Root
	selected={{ value: selectedOrgPlan }}
	onSelectedChange={(v) => {
		v && selectCb(v.value);
	}}
>
	<Select.Trigger asChild let:builder>
		<Button
			data-testid="org-plan-select-btn"
			builders={[builder]}
			variant="outline-neutral"
			title="Select plan"
			class={cn(
				'flex items-center justify-between gap-8 pl-3 pr-2 mb-1 h-10 min-w-full bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent rounded-md',
				className
			)}
		>
			<span class="whitespace-nowrap line-clamp-1 font-normal text-left capitalize">
				{capitalize(selectedOrgPlan.replace('_', ''))} - ${$page.data.prices.plans[selectedOrgPlan]
					?.flat_amount_decimal}/month
			</span>

			<ChevronDown class="h-4 w-4" />
		</Button>
	</Select.Trigger>
	<Select.Content sameWidth class="max-h-64 overflow-y-auto">
		{#each Object.keys($page.data.prices.plans).filter((key) => !key.startsWith('_')) as key}
			{@const plan = $page.data.prices.plans[key]}
			<Select.Item
				value={key}
				labelSelected
				label={capitalize(`${key} - $${plan.flat_amount_decimal}/month`)}
				class="flex justify-between gap-10 cursor-pointer"
			>
				{capitalize(`${key} - $${plan.flat_amount_decimal}/month`)}
			</Select.Item>
		{/each}
	</Select.Content>
</Select.Root>
