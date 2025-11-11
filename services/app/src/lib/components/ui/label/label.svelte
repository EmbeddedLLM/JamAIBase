<script lang="ts">
	import { Label as LabelPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		class: className,
		required = false,
		children,
		...restProps
	}: LabelPrimitive.RootProps & { required?: boolean } = $props();
</script>

<LabelPrimitive.Root
	bind:ref
	class={cn(
		'text-left text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
		className
	)}
	{...restProps}
>
	{@render children?.()}
	{#if required}
		<span class="pl-0.5 text-sm font-medium text-destructive">*</span>
	{/if}
</LabelPrimitive.Root>
