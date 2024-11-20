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
		"absolute px-1.5 py-[3px] text-xs bg-[#1D2939] text-white rounded-sm after:content-[''] after:absolute after:left-1/2 after:-translate-x-1/2 pointer-events-none transition-opacity",
		showArrow ? 'after:block' : 'after:hidden',
		className
	)}
>
	<slot />
</span>

<style>
	span::after {
		bottom: -(calc(10px + var(--arrow-size)));
		border-top: var(--arrow-size) solid #1d2939;
		border-bottom: var(--arrow-size) solid transparent;
		border-left: var(--arrow-size) solid transparent;
		border-right: var(--arrow-size) solid transparent;
	}
</style>
