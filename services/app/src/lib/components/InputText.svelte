<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { cn } from '$lib/utils';

	import { Button } from '$lib/components/ui/button';
	import EyeOffIcon from '$lib/icons/EyeOffIcon.svelte';
	import EyeOnIcon from '$lib/icons/EyeOnIcon.svelte';

	let className: string | undefined | null = undefined;
	export { className as class };
	export let type: string | undefined = undefined;
	export let value: any = '';
	export let obfuscate: boolean = false;

	const dispatch = createEventDispatcher<{
		input: Event & {
			currentTarget: EventTarget & HTMLInputElement;
		};
	}>();

	$: inputClass = cn(
		`${obfuscate ? 'pl-3 pr-12' : 'px-3'} py-2 w-full text-sm placeholder:italic bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors`,
		className
	);
	let showVal = false;

	function handleInput(e: Event & { currentTarget: EventTarget & HTMLInputElement }) {
		dispatch('input', e);
		value = e.currentTarget.value;
	}
</script>

<div class="relative w-full">
	<slot name="leading" />

	{#if type === 'search'}
		<input {...$$restProps} bind:value on:input={handleInput} type="search" class={inputClass} />
	{:else if obfuscate && !showVal}
		<input
			{...$$restProps}
			bind:value
			on:input={handleInput}
			autocomplete="new-password"
			type="password"
			class={inputClass}
		/>
	{:else}
		<input
			{...$$restProps}
			bind:value
			on:input={handleInput}
			autocomplete={obfuscate ? 'new-password' : undefined}
			type="text"
			class={inputClass}
		/>
	{/if}

	{#if obfuscate}
		<Button
			variant="ghost"
			title="Show / hide"
			on:click={() => (showVal = !showVal)}
			class="absolute top-1/2 right-2 -translate-y-1/2 p-0 h-7 rounded-full aspect-square"
		>
			{#if showVal}
				<EyeOnIcon class="h-5" />
			{:else}
				<EyeOffIcon class="h-5" />
			{/if}
		</Button>
	{/if}
</div>
