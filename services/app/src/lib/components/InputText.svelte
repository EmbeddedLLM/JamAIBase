<script lang="ts">
	import { cn } from '$lib/utils';

	import { Button } from '$lib/components/ui/button';
	import EyeOffIcon from '$lib/icons/EyeOffIcon.svelte';
	import EyeOnIcon from '$lib/icons/EyeOnIcon.svelte';

	interface Props {
		class?: string | undefined | null;
		type?: string | undefined;
		value?: any;
		obfuscate?: boolean;
		leading?: import('svelte').Snippet;
		[key: string]: any;
	}

	let {
		class: className = undefined,
		type = undefined,
		value = $bindable(),
		obfuscate = false,
		leading,
		...rest
	}: Props = $props();

	let inputClass = $derived(
		cn(
			`${obfuscate ? 'pl-3 pr-12' : 'px-3'} h-10 py-2 w-full text-sm placeholder:italic bg-[#E4E7EC] data-dark:bg-[#42464e] rounded-lg border border-transparent placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors`,
			className
		)
	);
	let showVal = $state(false);
</script>

<div class="relative w-full">
	{@render leading?.()}

	{#if type === 'search'}
		<input bind:value type="search" class={inputClass} {...rest} />
	{:else if obfuscate && !showVal}
		<input bind:value autocomplete="new-password" type="password" class={inputClass} {...rest} />
	{:else}
		<input
			bind:value
			autocomplete={obfuscate ? 'new-password' : undefined}
			type="text"
			class={inputClass}
			{...rest}
		/>
	{/if}

	{#if obfuscate}
		<Button
			variant="ghost"
			title="Show / hide"
			onclick={() => (showVal = !showVal)}
			class="absolute right-2 top-1/2 aspect-square h-7 -translate-y-1/2 rounded-full p-0"
		>
			{#if showVal}
				<EyeOnIcon class="h-5" />
			{:else}
				<EyeOffIcon class="h-5" />
			{/if}
		</Button>
	{/if}
</div>
