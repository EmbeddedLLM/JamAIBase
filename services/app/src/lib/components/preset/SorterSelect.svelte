<script lang="ts">
	import type { ComponentType } from 'svelte';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { cn } from '$lib/utils';

	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';

	export let sortOptions: { orderBy: string; order: 'asc' | 'desc' };
	export let sortableFields: { id: string; title: string; Icon: ComponentType }[];
	export let refetchTables: () => Promise<void>;
	let className: string | undefined | null = undefined;
	export { className as class };
</script>

<Select.Root
	selected={{ value: sortOptions }}
	onSelectedChange={(e) => {
		if (e) {
			sortOptions = e.value;
			refetchTables();
		}
	}}
>
	<Select.Trigger asChild let:builder>
		<Button
			builders={[builder]}
			variant="ghost"
			title="Sort options"
			class={cn(
				'flex gap-1 px-2 py-0.5 sm:py-1 h-[unset] sm:min-w-64 text-xs sm:text-sm text-[#475467] hover:text-[#475467]',
				className
			)}
		>
			{@const { title, Icon } =
				sortableFields.find((field) => field.id === sortOptions.orderBy) ?? {}}
			{#key title}
				<Icon ascending={sortOptions.order === 'asc'} class="h-7 w-7" />
			{/key}

			<span class="block w-full whitespace-nowrap line-clamp-1 font-normal text-left">
				{title}
				{sortOptions.order === 'asc' ? '(Ascending)' : '(Descending)'}
			</span>

			<ChevronDown class="flex-[0_0_auto] h-5 w-5" />
		</Button>
	</Select.Trigger>
	<Select.Content sameWidth side="bottom" class="max-h-64 overflow-y-auto">
		{#each sortableFields as { id, title, Icon }}
			{#each ['asc', 'desc'] as direction}
				<Select.Item
					title="{title} {direction === 'asc' ? '(Ascending)' : '(Descending)'}"
					value={{ orderBy: id, order: direction }}
					label="{title} {direction === 'asc' ? '(Ascending)' : '(Descending)'}"
					labelSelected
					selectedLabelPosition="right"
					class="relative gap-1 cursor-pointer"
				>
					<Icon ascending={direction === 'asc'} class="flex-[0_0_auto] h-[22px] w-[22px]" />
					{title}
					{direction === 'asc' ? '(Ascending)' : '(Descending)'}
				</Select.Item>
			{/each}
		{/each}
	</Select.Content>
</Select.Root>
