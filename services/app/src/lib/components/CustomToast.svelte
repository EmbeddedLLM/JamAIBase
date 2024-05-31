<script lang="ts">
	import { fade } from 'svelte/transition';

	import { Button } from '$lib/components/ui/button';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	export let title: string;
	export let subtitle: string;
	export let type: 'success' | 'error' | 'warning' | 'info' = 'success';
	export let closeCb: () => void;

	const typesBar = {
		success: 'bg-success',
		error: 'bg-destructive',
		warning: 'bg-warning',
		info: 'bg-blue-500'
	};

	const typesBg = {
		success: 'data-dark:bg-success/[0.28]',
		error: 'data-dark:bg-destructive/[0.28]',
		warning: 'data-dark:bg-warning/[0.28]',
		info: 'data-dark:bg-blue-500/[0.28]'
	};
</script>

<div
	in:fade={{ duration: 150 }}
	out:fade={{ duration: 150 }}
	class="absolute top-8 right-8 transition-opacity duration-200 z-[999]"
>
	<div
		class={`relative flex items-center gap-8 p-6 bg-white ${typesBg[type]} rounded-lg shadow-[0px_0px_8px_0px] shadow-black/25 overflow-hidden`}
	>
		<div class={`absolute top-0 bottom-0 left-0 w-2 ${typesBar[type]}`} />

		<div class="flex flex-col gap-1">
			<span>{title}</span>

			<span class="text-[#999999] data-dark:text-[#C9C9C9] text-sm">{subtitle}</span>
		</div>

		<Button variant="ghost" on:click={closeCb} class="p-0 aspect-square">
			<CloseIcon class="w-6 h-6" />
		</Button>
	</div>
</div>
