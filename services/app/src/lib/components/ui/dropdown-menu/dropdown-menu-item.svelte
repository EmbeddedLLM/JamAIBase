<script lang="ts">
	import { DropdownMenu as DropdownMenuPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';

	type $$Props = DropdownMenuPrimitive.ItemProps & {
		inset?: boolean;
	};
	type $$Events = DropdownMenuPrimitive.ItemEvents;

	let className: $$Props['class'] = undefined;
	export let inset: $$Props['inset'] = undefined;
	export { className as class };
</script>

<DropdownMenuPrimitive.Item
	class={cn(
		'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm text-[#344054] outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-[#F2F4F7] data-[highlighted]:text-[#344054] data-[disabled]:opacity-50',
		inset && 'pl-8',
		className
	)}
	{...$$restProps}
	on:click
	on:keydown
	on:focusin
	on:focusout
	on:pointerdown
	on:pointerleave
	on:pointermove
	let:builder
>
	<slot {builder} />
</DropdownMenuPrimitive.Item>
