<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class={className}>
	<circle cx="256" cy="256" r="48" fill="currentColor" />
	<circle cx="256" cy="416" r="48" fill="currentColor" />
	<circle cx="256" cy="96" r="48" fill="currentColor" />
</svg>
