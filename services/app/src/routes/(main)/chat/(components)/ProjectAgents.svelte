<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import type { GenTable, Project } from '$lib/types';

	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	let {
		project,
		agents,
		loadingAgents
	}: { project: Project; agents: GenTable[]; loadingAgents: boolean } = $props();
</script>

<div class="mt-5 flex flex-col first-of-type:mt-0">
	<span class="mx-4 text-sm font-medium uppercase text-[#98A2B3]">{project.name}</span>

	<ul class="grid grid-cols-[repeat(auto-fill,_minmax(13rem,_1fr))] gap-3 px-4 py-3">
		{#each agents as agent (agent.id)}
			<button
				title={agent.id}
				onclick={() => {
					page.url.searchParams.append('project_id', project.id);
					page.url.searchParams.append('agent', agent.id);
					goto(`?${page.url.searchParams}`, { replaceState: true });
				}}
				class="flex flex-[0_0_auto] gap-1 rounded-lg border border-transparent bg-[#F2F4F7] px-2 py-2 text-sm text-[#475467] transition-colors hover:border-[#FFD8DF] hover:bg-[#FFF7F8] hover:text-[#950048]"
			>
				<ChatAgentIcon class="h-5 flex-[0_0_auto]" />
				<span class="line-clamp-1 break-all">{agent.id}</span>
			</button>
		{/each}
		{#if loadingAgents}
			<div class="flex items-center justify-center p-2">
				<LoadingSpinner class="h-4 w-4 text-secondary" />
			</div>
		{/if}
	</ul>
</div>
