<script lang="ts">
	import { cn } from '$lib/utils.js';

	let className: string | undefined = undefined;
	export { className as class };
</script>

<div
	class={cn(
		'flex justify-end px-8 py-2.5 self-end w-full bg-[#f6f6f6] data-dark:bg-[#42464e] border-t border-[#DDD] data-dark:border-[#42464E] rounded-b-xl',
		className
	)}
>
	<slot />
</div>
