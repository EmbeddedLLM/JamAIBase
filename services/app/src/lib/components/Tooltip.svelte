<script lang="ts">
	import { cn } from '$lib/utils';

	export let tooltip: HTMLSpanElement | undefined = undefined;
	export let style: string | undefined | null = undefined;
	let className: string | undefined | null = undefined;
	export { className as class };

	export let showArrow = true;
	export let arrowSize = 10;
</script>

<span
	bind:this={tooltip}
	style="--arrow-size: {arrowSize}px; {style || ''}"
	class={cn(
		"absolute p-2 bg-black text-white rounded-lg after:content-[''] after:absolute after:left-3 after:-bottom-5 pointer-events-none transition-opacity",
		showArrow ? 'after:block' : 'after:hidden',
		className
	)}
>
	<slot />
</span>

<style>
	span::after {
		border-top: var(--arrow-size) solid black;
		border-bottom: var(--arrow-size) solid transparent;
		border-left: var(--arrow-size) solid transparent;
		border-right: var(--arrow-size) solid transparent;
	}
</style>
