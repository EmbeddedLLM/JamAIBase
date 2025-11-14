<script lang="ts">
	import { cn } from '$lib/utils';

	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';

	interface Props {
		searchQuery: string;
		debouncedSearch: (q: string) => Promise<void> | undefined;
		isLoadingSearch: boolean;
		label?: string;
		placeholder?: string;
		class?: string | undefined | null;
	}

	let {
		searchQuery = $bindable(),
		debouncedSearch,
		isLoadingSearch,
		label = 'Search',
		placeholder = 'Search',
		class: className = undefined
	}: Props = $props();
</script>

<div class={cn('relative w-full', className)}>
	<input
		oninput={(e) => debouncedSearch(e.currentTarget.value)}
		bind:value={searchQuery}
		aria-label={label}
		{placeholder}
		class="h-8 w-full rounded-lg border border-transparent bg-[#E4E7EC] px-3 py-2 pl-8 text-sm transition-colors placeholder:not-italic placeholder:text-[#98A2B3] focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5] sm:h-9"
	/>

	{#if isLoadingSearch}
		<div class="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 sm:left-3">
			<LoadingSpinner class="h-3" />
		</div>
	{:else}
		<SearchIcon
			class="pointer-events-none absolute left-[9px] top-1/2 h-3 -translate-y-1/2 text-[#667085] sm:left-3"
		/>
	{/if}
</div>
