<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import CheckDoneIcon from '$lib/icons/CheckDoneIcon.svelte';
	import CopyIcon from '$lib/icons/CopyIcon.svelte';

	interface Props {
		description: string;
		requestID: string;
	}

	let { description, requestID }: Props = $props();

	let requestIDCopied = $state(false);
	let requestIDCopiedTimeout: ReturnType<typeof setTimeout> | undefined = $state();
</script>

<div class="flex flex-col gap-1 group-[.toast]:text-muted-foreground">
	<p class="text-muted-foreground">{description}</p>
	{#if requestID}
		<div class="flex w-max items-center gap-0.5 rounded-lg bg-[#0C111D] px-2 py-1.5">
			<span class="text-white">{requestID}</span>
			<Button
				variant="ghost"
				aria-label="Copy organization ID"
				onclick={() => {
					navigator.clipboard.writeText(requestID);
					clearTimeout(requestIDCopiedTimeout);
					requestIDCopied = true;
					requestIDCopiedTimeout = setTimeout(() => (requestIDCopied = false), 1500);
				}}
				class="relative aspect-square h-6 rounded-full p-[1px] text-muted-foreground hover:bg-white"
			>
				<CopyIcon
					class="absolute h-4 {requestIDCopied ? 'opacity-0' : 'opacity-100'} transition-opacity"
				/>
				<CheckDoneIcon
					class="absolute h-4 {requestIDCopied ? 'opacity-100' : 'opacity-0'} transition-opacity"
				/>
			</Button>
		</div>
	{/if}
</div>
