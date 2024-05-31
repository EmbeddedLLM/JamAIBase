<script lang="ts">
	import { cn } from '$lib/utils.js';
	import Check from 'lucide-svelte/icons/check';
	import { Select as SelectPrimitive } from 'bits-ui';

	type $$Props = SelectPrimitive.ItemProps & { labelSelected?: boolean };
	type $$Events = SelectPrimitive.ItemEvents;

	let className: $$Props['class'] = undefined;
	export let value: $$Props['value'];
	export let label: $$Props['label'] = undefined;
	export let disabled: $$Props['disabled'] = undefined;
	export { className as class };
	export let labelSelected = false;
</script>

<SelectPrimitive.Item
	{value}
	{disabled}
	{label}
	class={cn(
		'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pr-2 text-sm outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[selected]:bg-[#F7F7F7] data-[selected]:text-black data-[disabled]:opacity-50',
		labelSelected ? 'pl-8' : 'pl-2',
		className
	)}
	{...$$restProps}
	on:click
	on:keydown
	on:focusin
	on:focusout
	on:pointerleave
	on:pointermove
>
	{#if labelSelected}
		<span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
			<SelectPrimitive.ItemIndicator>
				<Check class="h-4 w-4" />
			</SelectPrimitive.ItemIndicator>
		</span>
	{/if}
	<slot>
		{label ? label : value}
	</slot>
</SelectPrimitive.Item>
