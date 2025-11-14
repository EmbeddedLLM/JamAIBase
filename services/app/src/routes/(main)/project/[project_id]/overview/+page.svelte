<script lang="ts">
	import { activeProject } from '$globalStore';
	import { Button } from '$lib/components/ui/button';
	import { Users2 } from '@lucide/svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>Overview</title>
</svelte:head>

<div class="grid h-full grid-cols-[minmax(300px,4fr)_minmax(0,10fr)]">
	<div class="flex flex-col px-6 py-3">
		<div class="h-[20rem] w-full bg-black">Placeholder picture</div>

		<p class="text-lg font-medium text-[#344054]">{$activeProject?.name}</p>

		<div class="flex flex-wrap gap-1">
			{#each $activeProject?.tags ?? [] as tag}
				<span class="text-[#e34972]">{tag}</span>
			{/each}
		</div>

		<Button>Edit Project Info</Button>

		<div class="flex flex-col">
			<div class="flex items-center">
				<Users2 />
				<span>
					{#await data.projectMembers}
						0
					{:then projectMembers}
						{projectMembers.data?.length}
					{/await}
				</span>
				members
			</div>
		</div>
	</div>

	<div class="my-3 mr-6 rounded-lg border border-[#E4E7EC] px-3 py-4">Description</div>
</div>
