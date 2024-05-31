<script lang="ts">
	import * as Dialog from '$lib/components/ui/dialog';
	import UploadingGraphic from '../UploadingGraphic.svelte';

	export let isUploadingFile: boolean;
</script>

<Dialog.Root onOutsideClick={(e) => e.preventDefault()} open={isUploadingFile}>
	<Dialog.Content class="min-h-[25rem] max-w-[24rem]">
		<div class="grow flex flex-col items-center justify-center gap-1 p-6 w-full overflow-auto">
			<UploadingGraphic class="h-52" />
			<span class="mt-4 text-lg">Generating</span>
			<span class="text-sm text-[#999]">On the way storming our brain...</span>
		</div>
	</Dialog.Content>
</Dialog.Root>
