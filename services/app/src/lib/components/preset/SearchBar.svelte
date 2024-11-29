<script lang="ts">
	import { cn } from '$lib/utils';

	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';

	export let searchQuery: string;
	export let debouncedSearch: (q: string) => Promise<void> | undefined;
	export let isLoadingSearch: boolean;
	export let label = 'Search';
	export let placeholder = 'Search';
	let className: string | undefined | null = undefined;
	export { className as class };
</script>

<div
	class={cn(
		`relative flex items-center h-8 sm:h-9 ${
			searchQuery
				? 'w-[12rem] sm:w-[14rem] bg-[#F2F4F7]'
				: 'w-8 sm:w-9 has-[input:focus-visible]:w-[12rem] sm:has-[input:focus-visible]:w-[14rem] bg-[#F2F4F7] [&:not(:has(input:focus-visible))]:hover:bg-[#E4E7EC]'
		} rounded-full transition-[height,width,background-color] has-[input:focus-within]:bg-[#E4E7EC]`,
		className
	)}
>
	<input
		on:input={(e) => debouncedSearch(e.currentTarget.value)}
		bind:value={searchQuery}
		aria-label={label}
		{placeholder}
		class="pl-8 sm:pl-9 pr-4 py-[6.5px] sm:py-2 w-full text-xs sm:text-sm placeholder:text-[#98A2B3] bg-transparent focus-visible:outline-none {!searchQuery
			? 'cursor-pointer focus-visible:cursor-text'
			: ''} peer"
	/>

	{#if isLoadingSearch}
		<div class="absolute top-1/2 left-2.5 sm:left-3 -translate-y-1/2 pointer-events-none">
			<LoadingSpinner class="h-3" />
		</div>
	{:else}
		<SearchIcon
			class="absolute top-1/2 left-[9px] sm:left-3 -translate-y-1/2 h-3 text-[#667085] pointer-events-none"
		/>
	{/if}
</div>
