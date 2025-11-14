<script lang="ts">
	//see https://github.com/sveltejs/svelte/issues/3088#issuecomment-1065827485
	import { onMount, onDestroy } from 'svelte';

	interface Props {
		target?: HTMLElement | null | undefined;
		children?: import('svelte').Snippet;
	}

	let { target = globalThis.document?.body, children }: Props = $props();

	let ref: HTMLElement | undefined = $state();

	onMount(() => {
		if (target && ref) {
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
	{@render children?.()}
</div>
