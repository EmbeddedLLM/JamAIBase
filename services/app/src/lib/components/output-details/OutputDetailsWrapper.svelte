<script lang="ts">
	import type { TableState } from '$lib/components/tables/tablesState.svelte';
	import OutputDetails from '$lib/components/output-details/OutputDetails.svelte';
	import type { ChatState } from '../../../routes/(main)/chat/chat.svelte';

	let {
		showOutputDetails = $bindable()
	}: {
		showOutputDetails: TableState['showOutputDetails'] | ChatState['showOutputDetails'];
	} = $props();

	let showActual = $state(showOutputDetails.open);

	function closeOutputDetails() {
		showOutputDetails = { ...showOutputDetails, open: false };
	}
</script>

<!-- barrier dismissable -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="absolute inset-0 z-30 {showOutputDetails.open
		? 'pointer-events-auto opacity-100'
		: 'pointer-events-none opacity-0'} transition-opacity duration-300"
	onclick={closeOutputDetails}
></div>

{#if showOutputDetails.open || showActual}
	<div
		data-testid="output-details-area"
		inert={!showOutputDetails.open}
		onanimationstart={() => {
			if (showOutputDetails.open) {
				showActual = true;
			}
		}}
		onanimationend={() => {
			if (!showOutputDetails.open) {
				showActual = false;
			}
		}}
		class="output-details fixed bottom-0 right-0 z-40 h-[clamp(0px,88%,100%)] px-4 py-3 {showOutputDetails.open
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
