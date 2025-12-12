<script lang="ts">
	import { getTableState } from '../tablesState.svelte';

	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import type { GenTableCol } from '$lib/types';

	const tableState = getTableState();

	let {
		colType,
		columnID,
		dtype,
		genConfig
	}: {
		colType: string;
		columnID: string;
		dtype: GenTableCol['dtype'];
		genConfig?: GenTableCol['gen_config'];
	} = $props();
</script>

<span
	style="background-color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
	class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-md p-[3px] text-xxs text-white sm:text-xs"
>
	<span class="px-1 font-medium capitalize">
		{#if colType === 'input'}
			Input
		{:else if genConfig?.object === 'gen_config.llm'}
			LLM
		{:else if genConfig?.object === 'gen_config.python'}
			Python
		{:else if genConfig?.object === 'gen_config.code'}
			Code
		{:else if genConfig?.object === 'gen_config.embed'}
			Embed
		{:else}
			Output
		{/if}
	</span>
	{#if !tableState.colSizes[columnID] || tableState.colSizes[columnID] >= 220}
		<span
			style="color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
			class="w-min select-none whitespace-nowrap rounded-[5px] bg-white px-1 font-medium"
		>
			{dtype}
		</span>
	{/if}

	{#if genConfig?.object === 'gen_config.llm' && genConfig.multi_turn}
		<div
			style="color: {colType === 'input' ? '#7995E9' : '#FD853A'};"
			class="ml-0.5 w-min select-none whitespace-nowrap rounded-[5px] bg-white px-0.5 font-medium"
		>
			<MultiturnChatIcon class="h-[16px]" />
		</div>
	{/if}
</span>
