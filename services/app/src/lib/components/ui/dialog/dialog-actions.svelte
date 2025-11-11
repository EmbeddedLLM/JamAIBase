<script lang="ts">
	import { cn } from '$lib/utils.js';

	interface Props {
		class?: string | undefined;
		children?: import('svelte').Snippet;
	}

	let { class: className = undefined, children }: Props = $props();
	
</script>

<div
	class={cn(
		'flex justify-end px-4 sm:px-6 py-2 self-end w-full bg-white data-dark:bg-[#303338] border-t border-[#F2F4F7] data-dark:border-[#42464E] rounded-b-lg',
		className
	)}
>
	{@render children?.()}
</div>
