<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import CheckDoneIcon from '$lib/icons/CheckDoneIcon.svelte';
	import CopyIcon from '$lib/icons/CopyIcon.svelte';

	export let description: string;
	export let requestID: string;

	let requestIDCopied = false;
	let requestIDCopiedTimeout: ReturnType<typeof setTimeout>;
</script>

<div class="flex flex-col gap-0.5 group-[.toast]:text-muted-foreground">
	<p>{description}</p>
	{#if requestID}
		<div class="flex items-center gap-0.5">
			<span class="text-black">{requestID}</span>
			<Button
				variant="ghost"
				aria-label="Copy organization ID"
				on:click={() => {
					navigator.clipboard.writeText(requestID);
					clearTimeout(requestIDCopiedTimeout);
					requestIDCopied = true;
					requestIDCopiedTimeout = setTimeout(() => (requestIDCopied = false), 1500);
				}}
				class="relative p-[1px] h-6 rounded-full hover:bg-white aspect-square"
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
