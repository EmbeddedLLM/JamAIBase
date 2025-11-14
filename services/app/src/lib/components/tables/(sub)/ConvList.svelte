<script lang="ts">
	import ChevronsRight from 'lucide-svelte/icons/chevrons-right';
	import { showRightDock } from '$globalStore';
	import Conversations from './Conversations.svelte';
	import { Button } from '$lib/components/ui/button';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	let rightDockButton: HTMLButtonElement | undefined = $state();
	let showRightDockButton = $state(false);

	function mouseMoveListener(e: MouseEvent) {
		const chatWindow = document.getElementById('chat-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton?.contains(el) ||
			(chatWindow?.contains(el) &&
				chatWindow?.offsetWidth - (e.clientX - chatWindow?.offsetLeft) < 75)
		) {
			showRightDockButton = true;
		} else {
			showRightDockButton = false;
		}
	}

	function handleNewConv() {}
</script>

<svelte:document onmousemove={mouseMoveListener} />

<div class="relative flex h-screen flex-col border-l border-[#DDD] px-4 data-dark:border-[#2A2A2A]">
	<!-- Close right dock button -->
	<div
		class="pointer-events-none absolute -left-16 top-1/2 flex h-[80%] w-16 -translate-y-1/2 items-center justify-end overflow-hidden"
	>
		<button
			bind:this={rightDockButton}
			title="Show/hide past conversations"
			onclick={() => ($showRightDock = !$showRightDock)}
			onfocusin={() => (showRightDockButton = true)}
			onfocusout={() => (showRightDockButton = false)}
			class="rounded-l-xl border border-[#DDD] bg-white p-1 data-dark:border-[#2A2A2A] data-dark:bg-[#303338] {showRightDockButton
				? 'translate-x-0'
				: 'translate-x-11'} pointer-events-auto transition-transform duration-300"
		>
			<ChevronsRight class="h-8 w-8 {!$showRightDock && 'rotate-180'}" />
		</button>
	</div>

	<Button
		disabled={!$showRightDock}
		variant="outline"
		title="New conversation"
		onclick={handleNewConv}
		class="mt-6 flex w-full items-center gap-3 overflow-hidden whitespace-nowrap bg-transparent p-4 text-center"
	>
		<AddIcon class="h-3 w-3" />
		New conversation
	</Button>

	<Conversations />
</div>
