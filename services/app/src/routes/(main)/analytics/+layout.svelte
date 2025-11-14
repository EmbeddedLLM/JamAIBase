<script lang="ts">
	import 'chartjs-adapter-moment';

	import SelectMonth from './SelectMonth.svelte';
	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();
</script>

<svelte:head>
	<title>Analytics</title>
</svelte:head>

<section class="relative flex h-1 grow flex-col gap-4">
	<div class="relative flex items-start gap-2 pb-0 pl-7 pr-7 md:pr-6 md:pt-3">
		<div class="flex items-center gap-2 pt-0.5 text-[#344054]">
			<h1 class="text-xl">Overview</h1>
		</div>

		<SelectMonth />
	</div>

	{@render children?.()}
</section>
