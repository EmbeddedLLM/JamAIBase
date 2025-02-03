<script lang="ts">
	import ChevronsRight from 'lucide-svelte/icons/chevrons-right';
	import { showRightDock } from '$globalStore';
	import Conversations from './Conversations.svelte';
	import { Button } from '$lib/components/ui/button';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	let rightDockButton: HTMLButtonElement;
	let showRightDockButton = false;

	function mouseMoveListener(e: MouseEvent) {
		const chatWindow = document.getElementById('chat-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton.contains(el) ||
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

<svelte:document on:mousemove={mouseMoveListener} />

<div class="relative flex flex-col px-4 h-screen border-l border-[#DDD] data-dark:border-[#2A2A2A]">
	<!-- Close right dock button -->
	<div
		class="absolute top-1/2 -translate-y-1/2 -left-16 flex items-center justify-end h-[80%] w-16 overflow-hidden pointer-events-none"
	>
		<button
			bind:this={rightDockButton}
			title="Show/hide past conversations"
			on:click={() => ($showRightDock = !$showRightDock)}
			on:focusin={() => (showRightDockButton = true)}
			on:focusout={() => (showRightDockButton = false)}
			class="p-1 bg-white data-dark:bg-[#303338] border border-[#DDD] data-dark:border-[#2A2A2A] rounded-l-xl {showRightDockButton
				? 'translate-x-0'
				: 'translate-x-11'} transition-transform duration-300 pointer-events-auto"
		>
			<ChevronsRight class="w-8 h-8 {!$showRightDock && 'rotate-180'}" />
		</button>
	</div>

	<Button
		disabled={!$showRightDock}
		variant="outline"
		title="New conversation"
		on:click={handleNewConv}
		class="flex items-center gap-3 mt-6 p-4 w-full text-center bg-transparent whitespace-nowrap overflow-hidden"
	>
		<AddIcon class="w-3 h-3" />
		New conversation
	</Button>

	<Conversations />
</div>
