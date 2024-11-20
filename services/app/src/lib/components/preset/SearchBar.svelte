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
		`relative flex items-center ${
			searchQuery
				? 'w-[12rem] sm:w-[14rem] bg-white border border-[#E5E5E5]'
				: 'w-[8.5rem] has-[input:focus-visible]:w-[12rem] sm:has-[input:focus-visible]:w-[14rem] hover:bg-[#F2F4F7] has-[input:focus-visible]:bg-white border border-transparent'
		} has-[input:focus-visible]:border-[#66BEFE] has-[input:focus-visible]:shadow-[0px_0px_0.5px_1.5px] has-[input:focus-visible]:shadow-[#CAE7FD] rounded-full transition-all`,
		className
	)}
>
	<input
		on:input={(e) => debouncedSearch(e.currentTarget.value)}
		bind:value={searchQuery}
		aria-label={label}
		{placeholder}
		class="pl-8 sm:pl-9 pr-4 py-[6.5px] sm:py-2 w-full text-xs sm:text-sm placeholder:text-[#667085] bg-transparent focus-visible:outline-none {!searchQuery
			? 'cursor-pointer focus-visible:cursor-text'
			: ''} peer"
	/>

	{#if isLoadingSearch}
		<div class="absolute top-1/2 left-2.5 sm:left-3 -translate-y-1/2 pointer-events-none">
			<LoadingSpinner class="h-3" />
		</div>
	{:else}
		<SearchIcon
			class="absolute top-1/2 left-2.5 sm:left-3 -translate-y-1/2 h-3 text-[#667085] pointer-events-none"
		/>
	{/if}
</div>
