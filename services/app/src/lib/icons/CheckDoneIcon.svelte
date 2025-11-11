<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class={className}>
	<path
		fill="none"
		stroke="currentColor"
		stroke-linecap="round"
		stroke-linejoin="round"
		stroke-width="32"
		d="M464 128L240 384l-96-96m0 96l-96-96m320-160L232 284"
	/>
</svg>
