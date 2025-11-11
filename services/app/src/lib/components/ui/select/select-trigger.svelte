<script lang="ts">
	import { Select as SelectPrimitive, type WithoutChild } from 'bits-ui';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import { cn } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		class: className,
		children,
		showArrow = true,
		...restProps
	}: WithoutChild<SelectPrimitive.TriggerProps> & { showArrow?: boolean } = $props();
</script>

<SelectPrimitive.Trigger
	bind:ref
	class={cn(
		'flex h-10 w-full min-w-full items-center justify-between gap-8 rounded-lg border-transparent bg-[#F2F4F7] px-3 py-2 pl-3 pr-2 text-sm transition-colors placeholder:text-muted-foreground hover:bg-[#e1e2e6] disabled:cursor-not-allowed disabled:opacity-100 data-[placeholder]:italic data-[placeholder]:text-muted-foreground data-dark:bg-[#42464e] [&>span]:line-clamp-1',
		className
	)}
	{...restProps}
>
	{@render children?.()}
	{#if showArrow}
		<ChevronDown class="size-4 flex-[0_0_auto]" />
	{/if}
</SelectPrimitive.Trigger>
