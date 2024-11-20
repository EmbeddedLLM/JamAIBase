<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	type $$Props = HTMLAttributes<HTMLDivElement> & { disabledClose?: boolean };

	export let disabledClose = false;
	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<div
	data-testid="dialog-header"
	class={cn(
		'relative flex items-center justify-between px-4 py-3 h-min space-y-1.5 text-lg text-[#344054] font-medium text-left bg-white data-dark:bg-[#303338] rounded-t-lg',
		className
	)}
	{...$$restProps}
>
	<slot />
	<DialogPrimitive.Close
		disabled={disabledClose}
		class="flex items-center justify-center h-8 aspect-square hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
	>
		<CloseIcon class="w-6" />
		<span class="sr-only">Close</span>
	</DialogPrimitive.Close>

	<hr class="absolute left-0 bottom-0 w-full border-[#F2F4F7] data-dark:border-[#42464E]" />
</div>
