<script lang="ts">
	//see https://github.com/sveltejs/svelte/issues/3088#issuecomment-1065827485
	import { onMount, onDestroy } from 'svelte';

	export let target: HTMLElement | null | undefined = globalThis.document?.body;

	let ref: HTMLElement;

	onMount(() => {
		if (target) {
			target.appendChild(ref);
		}
	});

	onDestroy(() => {
		setTimeout(() => {
			if (ref?.parentNode) {
				ref.parentNode?.removeChild(ref);
			}
		});
	});
</script>

<div bind:this={ref}>
	<slot />
</div>
