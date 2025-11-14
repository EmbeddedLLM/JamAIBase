<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg viewBox="0 0 9 8" fill="none" xmlns="http://www.w3.org/2000/svg" class={className}>
	<path
		d="M4.5 0.5625V4M4.5 4V7.4375M4.5 4H8.09375M4.5 4L0.90625 4"
		stroke="currentColor"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
