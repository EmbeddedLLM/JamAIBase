<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	type $$Props = HTMLAttributes<HTMLDivElement>;

	let className: $$Props['class'] = undefined;
	export { className as class };
</script>

<div
	class={cn(
		'relative flex items-center justify-between px-5 pl-7 py-4 h-min space-y-1.5 text-xl font-bold text-center sm:text-left bg-[#f6f6f6] data-dark:bg-[#42464e] rounded-t-xl',
		className
	)}
	{...$$restProps}
>
	<slot />
	<DialogPrimitive.Close
		class="flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
	>
		<CloseIcon class="w-7" />
		<span class="sr-only">Close</span>
	</DialogPrimitive.Close>

	<hr class="absolute left-0 bottom-0 w-full border-[#DDD] data-dark:border-[#42464E]" />
</div>
