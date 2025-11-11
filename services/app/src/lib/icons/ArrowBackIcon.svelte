<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" class={className}>
	<path d="M14 9H4" stroke="#98A2B3" stroke-linecap="round" stroke-linejoin="round" />
	<path
		d="M6 7L4 9L6 11"
		stroke="#98A2B3"
		stroke-width="1.3"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
