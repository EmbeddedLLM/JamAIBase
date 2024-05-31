<script lang="ts">
	import { Button as ButtonPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';
	import { buttonVariants, type Props, type Events } from './index.js';

	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	type $$Props = Props & { loading?: boolean };
	type $$Events = Events;

	let className: $$Props['class'] = undefined;
	export let variant: $$Props['variant'] = 'default';
	export let size: $$Props['size'] = 'default';
	export let builders: $$Props['builders'] = [];
	export { className as class };

	export let loading: $$Props['loading'] = false;
</script>

<ButtonPrimitive.Root
	{builders}
	class={cn(buttonVariants({ variant, size, className }))}
	type="button"
	{...$$restProps}
	on:click
	on:keydown
>
	{#if loading}
		<LoadingSpinner class="data-dark:text-white" />
	{/if}

	<slot />
</ButtonPrimitive.Root>
