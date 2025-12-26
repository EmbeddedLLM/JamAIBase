<script lang="ts">
	import { guideConverter as converter } from '$lib/showdown';
	import type { GenTableCol } from '$lib/types';

	import llmHowToUse from './guides/llm.md?raw';
	import pythonHowToUse from './guides/python.md?raw';

	let {
		selectedGenConfig
	}: {
		selectedGenConfig: NonNullable<GenTableCol['gen_config']> | null;
	} = $props();

	const howToUseContent = $derived.by(() => {
		if (selectedGenConfig?.object === 'gen_config.llm') {
			return llmHowToUse;
		}

		if (selectedGenConfig?.object === 'gen_config.python') {
			return pythonHowToUse;
		}

		return '';
	});
</script>

<div class="overflow-auto px-4 py-3">
	<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
		{@html converter.makeHtml(howToUseContent)}
	</p>
</div>
