<script lang="ts">
	import { cn } from '$lib/utils.js';
	import Check from 'lucide-svelte/icons/check';
	import { Select as SelectPrimitive } from 'bits-ui';

	import LockIcon from '$lib/icons/LockIcon.svelte';

	type $$Props = SelectPrimitive.ItemProps & {
		labelSelected?: boolean;
		selectedLabelPosition?: 'left' | 'right';
	};
	type $$Events = SelectPrimitive.ItemEvents;

	let className: $$Props['class'] = undefined;
	export let value: $$Props['value'];
	export let label: $$Props['label'] = undefined;
	export let disabled: $$Props['disabled'] = undefined;
	export { className as class };
	export let labelSelected = false;
	export let selectedLabelPosition: 'left' | 'right' = 'left';
</script>

<SelectPrimitive.Item
	{value}
	{disabled}
	{label}
	class={cn(
		'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pr-2 text-sm outline-none data-[disabled]:pointer-events-none data-[highlighted]:text-accent-foreground data-[selected]:text-black data-[highlighted]:bg-[#F2F4F7] data-[selected]:!bg-[#F0F9FF] data-[disabled]:text-[#98A2B3]',
		labelSelected ? (selectedLabelPosition === 'left' ? 'pl-8' : 'pl-2 pr-8') : 'pl-2',
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
		{#if disabled}
			<span class="absolute left-1.5 flex h-[20px] w-[20px] items-center justify-center">
				<LockIcon class="h-5 w-5 text-[#98A2B3]" />
			</span>
		{:else}
			<span
				class="absolute {selectedLabelPosition === 'left'
					? 'left-2'
					: 'right-2'} flex h-3.5 w-3.5 items-center justify-center"
			>
				<SelectPrimitive.ItemIndicator>
					<Check class="h-4 w-4" />
				</SelectPrimitive.ItemIndicator>
			</span>
		{/if}
	{/if}
	<slot>
		{label ? label : value}
	</slot>
</SelectPrimitive.Item>
