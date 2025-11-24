<script lang="ts">
	import { getTableState, TableState } from '$lib/components/tables/tablesState.svelte';
	import OutputDetails from '$lib/components/output-details/OutputDetails.svelte';
	import type { ChatState } from '../../../routes/(main)/chat/chat.svelte';

	let {
		showOutputDetails = $bindable()
	}: {
		showOutputDetails: TableState['showOutputDetails'] | ChatState['showOutputDetails'];
	} = $props();

	const tableState = getTableState();

	let showActual = $state(tableState.showOutputDetails.open);

	function closeOutputDetails() {
		tableState.showOutputDetails = { ...tableState.showOutputDetails, open: false };
	}
</script>

<!-- Column settings barrier dismissable -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="absolute inset-0 z-30 {tableState.showOutputDetails.open
		? 'pointer-events-auto opacity-100'
		: 'pointer-events-none opacity-0'} transition-opacity duration-300"
	onclick={closeOutputDetails}
></div>

{#if tableState.showOutputDetails.open || showActual}
	<div
		data-testid="output-details-area"
		inert={!tableState.showOutputDetails.open}
		onanimationstart={() => {
			if (tableState.showOutputDetails.open) {
				showActual = true;
			}
		}}
		onanimationend={() => {
			if (!tableState.showOutputDetails.open) {
				showActual = false;
			}
		}}
		class="output-details fixed bottom-0 right-0 z-40 h-[clamp(0px,85%,100%)] px-4 py-3 {tableState
			.showOutputDetails.open
			? 'animate-in slide-in-from-right-full'
			: 'animate-out slide-out-to-right-full'} duration-300 ease-in-out"
	>
		<OutputDetails bind:showOutputDetails />
	</div>
{/if}

<style>
	.output-details {
		width: 100%;
	}

	@media (min-width: 800px) {
		.output-details {
			width: calc(100% * 5 / 6);
		}
	}

	@media (min-width: 1000px) {
		.output-details {
			width: calc(100% * 4 / 6);
		}
	}

	@media (min-width: 1200px) {
		.output-details {
			width: 50%;
		}
	}
</style>
