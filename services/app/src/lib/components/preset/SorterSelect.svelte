<script lang="ts">
	import type { Component } from 'svelte';
	import { cn } from '$lib/utils';

	import { m } from '$lib/paraglide/messages';
	import * as Select from '$lib/components/ui/select';
	import { MoveUp } from '@lucide/svelte';

	interface Props {
		sortOptions: { orderBy: string; order: 'asc' | 'desc' };
		sortableFields: { id: string; title: string; Icon: Component }[];
		refetchTables: () => Promise<void>;
		class?: string | undefined | null;
	}

	let {
		sortOptions = $bindable(),
		sortableFields,
		refetchTables,
		class: className = undefined
	}: Props = $props();
</script>

<Select.Root
	type="multiple"
	value={[sortOptions.orderBy, sortOptions.order]}
	onValueChange={(e) => {
		if (e.length < 2) return (sortOptions = sortOptions);
		const deltaOrderBy = sortableFields.find((field) => field.id === e[2])?.id;
		const deltaOrderDir = ['asc', 'desc'].find((dir) => dir === e[2]) as 'asc' | 'desc';
		sortOptions = {
			orderBy: deltaOrderBy ?? sortOptions.orderBy,
			order: (deltaOrderDir ?? sortOptions.order) as 'asc' | 'desc'
		};
		refetchTables();
	}}
>
	<Select.Trigger
		title="Sort options"
		class={cn(
			'flex h-[unset] items-center justify-center gap-1 whitespace-nowrap border-0 bg-[#E9EDFA] p-0 px-3 py-2 text-xs font-medium text-[#5478E4] ring-offset-background transition-colors hover:bg-[#D7DFF7] hover:text-[] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 sm:py-2 sm:text-sm',
			className
		)}
	>
		{#snippet children()}
			<!-- <Button
				variant="ghost"
				title="Sort options"
				class={cn(
					'flex h-[unset] gap-1 px-2 py-0.5 text-xs text-[#475467] hover:text-[#475467] sm:min-w-64 sm:py-1 sm:text-sm',
					className
				)}
			> -->
			{@const { title, Icon } =
				sortableFields.find((field) => field.id === sortOptions.orderBy) ?? {}}
			{#key title}
				<svg
					viewBox="0 0 7 9"
					fill="none"
					xmlns="http://www.w3.org/2000/svg"
					class="h-3 w-3 flex-[0_0_auto] {sortOptions.order === 'asc' ? 'rotate-180' : ''}"
				>
					<path d="M3.42188 1V8" stroke="#4169E1" stroke-linecap="round" stroke-linejoin="round" />
					<path
						d="M5.84615 5.57692L3.42308 8L1 5.57692"
						stroke="#4169E1"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>
			{/key}

			<span class="line-clamp-1 block w-full whitespace-nowrap text-left font-normal">
				{title}
			</span>
		{/snippet}
	</Select.Trigger>
	<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
		<span class="pointer-events-none mb-1 ml-1 text-[12px] font-medium uppercase text-[#98A2B3]">
			Sort by
		</span>
		{#each sortableFields as { id, title, Icon }}
			<Select.Item {title} value={id} label={title} class="relative cursor-pointer gap-1">
				<!-- <Icon ascending={direction === 'asc'} class="h-[22px] w-[22px] flex-[0_0_auto]" /> -->
				{title}
			</Select.Item>
		{/each}

		<hr class="-mx-1 my-1" />

		<span class="pointer-events-none mb-1 ml-1 text-[12px] font-medium uppercase text-[#98A2B3]">
			Order
		</span>
		{#each ['asc', 'desc'] as direction}
			<Select.Item
				title={direction === 'asc'
					? `${m['sortable.direction_asc']()}`
					: `${m['sortable.direction_desc']()}`}
				value={direction}
				label={direction === 'asc'
					? `${m['sortable.direction_asc']()}`
					: `${m['sortable.direction_desc']()}`}
				class="relative cursor-pointer gap-1"
			>
				<!-- <Icon ascending={direction === 'asc'} class="h-[22px] w-[22px] flex-[0_0_auto]" /> -->
				{direction === 'asc'
					? `${m['sortable.direction_asc']()}`
					: `${m['sortable.direction_desc']()}`}
			</Select.Item>
		{/each}
	</Select.Content>
</Select.Root>
