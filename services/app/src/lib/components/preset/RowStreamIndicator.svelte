<script lang="ts">
	import { onDestroy, onMount } from 'svelte';

	let divCircles: HTMLDivElement[] = $state([]);

	let interval: NodeJS.Timeout;
	let index = 0;
	onMount(() => {
		interval = setInterval(() => {
			divCircles.forEach((divCircle, _index) => {
				if (_index !== index) {
					divCircle.style.backgroundColor = '#CACCCF';
				} else {
					divCircle.style.backgroundColor = '#A1A4B1';
				}
			});
			index = (index + 1) % divCircles.length;
		}, 200);
	});

	onDestroy(() => {
		clearInterval(interval);
	});
</script>

<div
	class="flex items-center justify-center gap-1 p-1 w-min bg-white border border-[#E4E7EC] data-dark:border-[#333] rounded-full pointer-events-none"
>
	{#each Array(3) as _, index}
		<div
			bind:this={divCircles[index]}
			class="h-1.5 bg-[#CACCCF] rounded-full aspect-square transition-colors"
		></div>
	{/each}
</div>
