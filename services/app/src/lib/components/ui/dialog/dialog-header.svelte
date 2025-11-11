<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import type { WithElementRef } from 'bits-ui';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	let {
		ref = $bindable(null),
		class: className,
		children,
		disabledClose = false,
		...restProps
	}: WithElementRef<HTMLAttributes<HTMLDivElement>> & { disabledClose?: boolean } = $props();
</script>

<div
	data-testid="dialog-header"
	bind:this={ref}
	class={cn(
		'relative flex h-min items-center justify-between space-y-1.5 rounded-t-lg bg-white px-4 py-3 text-left text-lg font-medium text-[#344054] data-dark:bg-[#303338]',
		className
	)}
	{...restProps}
>
	{@render children?.()}

	<DialogPrimitive.Close
		disabled={disabledClose}
		class="flex aspect-square h-8 items-center justify-center rounded-full !bg-transparent ring-offset-background transition-colors hover:!bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
	>
		<CloseIcon class="w-6" />
		<span class="sr-only">Close</span>
	</DialogPrimitive.Close>

	<hr class="absolute bottom-0 left-0 w-full border-[#F2F4F7] data-dark:border-[#42464E]" />
</div>
