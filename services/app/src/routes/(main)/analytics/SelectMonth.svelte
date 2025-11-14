<script lang="ts">
	import { addMonths, differenceInMonths, fromUnixTime, isThisMonth } from 'date-fns';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	import LeftArrowIcon from '$lib/icons/LeftArrowIcon.svelte';

	let month = $state(-1);
	$effect(() => {
		month = parseInt(page.url.searchParams.get('month') ?? '');
	});
	$effect(() => {
		if (isNaN(month)) {
			month = differenceInMonths(new Date(), fromUnixTime(0));
		}
	});
	let selectedCurrentMonth = $derived(isThisMonth(addMonths(fromUnixTime(0), month)));

	function navigateMonths(diff: number) {
		if (month !== -1) {
			month += diff;
			if (month === differenceInMonths(new Date(), fromUnixTime(0))) goto(page.url.pathname);
			else goto(`?month=${month}`);
		}
	}
</script>

<div
	class="flex items-center justify-center gap-1 rounded-md border border-[#E4E7EC] bg-white text-sm text-[#475467] data-dark:border-[#333] data-dark:bg-[#42464E]"
>
	<button
		title="Previous month"
		onclick={() => navigateMonths(-1)}
		class="h-full rounded px-2 py-2.5 transition-colors hover:bg-gray-100 focus:outline-none"
	>
		<LeftArrowIcon class="h-3 text-gray-700" />
	</button>
	<div class="cursor-default">
		{addMonths(fromUnixTime(0), month).toLocaleString(undefined, {
			month: 'short',
			year: 'numeric'
		})}
	</div>
	<button
		title="Next month"
		disabled={selectedCurrentMonth}
		onclick={() => navigateMonths(1)}
		class="h-full rounded px-2 py-2.5 focus:outline-none {!selectedCurrentMonth &&
			'hover:bg-gray-100'} transition-colors"
	>
		<LeftArrowIcon class="h-3 text-gray-600 {selectedCurrentMonth && 'text-gray-300'} rotate-180" />
	</button>
</div>
