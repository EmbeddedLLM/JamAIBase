<script lang="ts">
	import debounce from 'lodash/debounce';
	import { MediaQuery } from 'svelte/reactivity';
	import { MessageCirclePlus, Trash2 } from '@lucide/svelte';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import { afterNavigate, goto } from '$app/navigation';
	import { preferredTheme, showDock } from '$globalStore';
	import { chatState } from './chat/chat.svelte.js';
	import { cn } from '$lib/utils';

	import longWhiteLogo from '$lib/assets/Jamai-Long-White-Main.svg';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';

	import { m } from '$lib/paraglide/messages';
	import { DeleteConvDialog } from './chat/[project_id]/[conversation_id]/(components)';
	import { Button } from '$lib/components/ui/button';
	import InputText from '$lib/components/InputText.svelte';
	import Jambu from '$lib/icons/Jambu.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SideBarIcon from '$lib/icons/SideBarIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import DeleteIcon from '$lib/icons/DeleteIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	const bigScreen = new MediaQuery('min-width: 768px', true);

	let isEditingTitle = $state<string | null>(null);
	let editedTitle = $state('');
	let saveEditBtn = $state<HTMLButtonElement>();
	let isDeletingConv = $state<string | null>(null);

	let currentTheme = $derived($preferredTheme == 'DARK' ? 'dark' : 'light');
	$effect(() => {
		if (browser) {
			if ($preferredTheme == 'SYSTEM') {
				currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';
			}
		}
	});

	const debouncedSearchConvs = debounce((e) => {
		chatState.searchQuery = e.target?.value;
		chatState.isLoadingSearch = true;
		chatState.refetchConversations();
	}, 300);

	let projectId = $derived(page.params.project_id || page.url.searchParams.get('project_id'));
	$effect(() => {
		projectId;
		chatState.refetchConversations();
	});

	//* Load more conversations when scrolling down
	const debouncedScrollHandler = debounce(async (e: Event) => {
		const target = e.target as HTMLUListElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !chatState.isLoadingMoreConvs && !chatState.moreConvsFinished) {
			await chatState.getConversations();
		}
	}, 300);

	afterNavigate(() => {
		if (!bigScreen.current) {
			$showDock = false;
		}
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	onclick={() => ($showDock = false)}
	class="absolute bottom-0 left-0 right-0 top-0 z-[999] block bg-black md:hidden {$showDock
		? 'opacity-50'
		: 'pointer-events-none opacity-0'} transition-opacity duration-200"
></div>

<div
	inert={!bigScreen.current && !$showDock}
	class="fixed bottom-0 left-0 top-0 z-[9999] transition-transform duration-300 md:static md:z-[1] md:py-3 md:pl-3 {$showDock
		? 'translate-x-0'
		: '-translate-x-full md:translate-x-0'}"
>
	<nav
		class="z-[1] flex h-full max-h-screen w-[250px] flex-col border-r border-[#DDD] bg-white transition-[border-radius] duration-500 data-dark:border-[#2A2A2A] data-dark:bg-[#303338] md:max-h-[calc(100vh-24px)] md:w-auto {$showDock
			? 'md:rounded-2xl'
			: 'md:rounded-[32px]'} md:border-r-transparent md:shadow-[0px_1px_4px_0px_#1018281A]"
	>
		<div
			class="flex justify-between py-4 {$showDock
				? 'px-4'
				: 'md:mb-2'} transition-[margin,padding] duration-200"
		>
			<img
				width="116"
				src={currentTheme == 'dark' ? longWhiteLogo : longBlackLogo}
				alt=""
				class="{$showDock || !bigScreen.current
					? 'md:scale-100'
					: 'w-0 md:scale-0'} transition-[transform,width] duration-300"
			/>

			<Button
				variant="ghost"
				title={m['left_dock.show_hide_btn']()}
				onclick={() => ($showDock = !$showDock)}
				class="visible aspect-square h-12 w-12 flex-[0_0_auto] rounded-full p-0 md:invisible {$showDock
					? 'md:translate-x-0'
					: 'md:-translate-x-[3.5px]'} group transition-[transform,background-color] duration-200"
			>
				<SideBarIcon class="scale-125 [&_*]:stroke-[1.3]" />
			</Button>
		</div>

		<div
			data-expanded={$showDock}
			class="relative flex grow flex-col pb-2 {$showDock || !bigScreen.current
				? 'px-2'
				: 'px-1'} group overflow-y-auto overflow-x-hidden transition-[padding,margin] duration-300"
		>
			<a
				title="Switch to JamAI Base"
				href="/project"
				style="background: linear-gradient(224.34deg, #e280a3 15.61%, #ffc1d7 49.6%, #e280a3 83.58%); box-shadow: 0px 1px 3px 0px rgba(16, 24, 40, 0.1);;"
				class={cn(
					'group/link relative flex w-full flex-[0_0_auto] items-center whitespace-nowrap p-px text-[#A62050] transition-all',
					$showDock || !bigScreen.current
						? 'h-9 rounded-md'
						: 'h-11 w-11 translate-x-[1.5px] rounded-[50%]'
				)}
			>
				<div
					style="background: linear-gradient(267.77deg, #FFEFF2 45.75%, #FFF7DD 100%);"
					class={cn(
						'flex h-full w-full flex-[0_0_auto] items-center transition-all',
						$showDock || !bigScreen.current
							? 'gap-2 rounded-[calc(var(--radius)_-_3px)] px-4 py-3'
							: 'gap-0 rounded-[50%]'
					)}
				>
					<Jambu
						class={cn(
							'absolute h-[30px] w-[30px] flex-[0_0_auto] text-[#344054] group-data-[expanded=false]:h-[38px] group-data-[expanded=false]:w-[38px] data-dark:text-white [&_path]:stroke-[1.5]',
							$showDock || !bigScreen.current
								? 'left-2.5 [transition:height_100ms_ease-in-out,_width_100ms_ease-in-out,_left_100ms_ease-in-out,_transform_100ms_ease-in-out,_color_150ms]'
								: 'left-1/2 -translate-x-1/2 [transition:height_200ms_ease-in-out,_width_200ms_ease-in-out,_left_200ms_ease-in-out_150ms,_transform_200ms_ease-in-out_150ms,_color_150ms]'
						)}
					/>

					<span
						class={cn(
							'absolute left-12 text-sm font-medium transition-[opacity,left] duration-200',
							$showDock ? 'opacity-100' : 'pointer-events-none opacity-0'
						)}
					>
						Switch to JamAI Base
					</span>
				</div>
			</a>

			<hr class="my-1 border-[#E5E5E5] transition-[margin] data-dark:border-[#484C55]" />

			<a
				href={chatState.conversation
					? `/chat?${new URLSearchParams([
							['project_id', page.params.project_id],
							['agent', chatState.conversation.parent_id ?? '']
						])}`
					: '/chat'}
				class={cn(
					'group/link relative flex w-full flex-[0_0_auto] items-center whitespace-nowrap text-[#344054] transition-all hover:bg-[#F2F4F7] data-dark:text-white data-dark:hover:bg-white/[0.04]',
					$showDock || !bigScreen.current
						? 'h-9 gap-2 rounded-md px-4 py-3'
						: 'h-11 w-11 translate-x-[1.5px] gap-0 rounded-full p-3'
				)}
			>
				<MessageCirclePlus
					class={cn(
						'absolute h-[18px] w-[18px] flex-[0_0_auto] text-[#344054] group-data-[expanded=false]:h-[22px] group-data-[expanded=false]:w-[22px] data-dark:text-white [&_path]:stroke-[1.5]',
						$showDock || !bigScreen.current
							? 'left-4 [transition:left_100ms_ease-in-out,_transform_100ms_ease-in-out,_color_150ms]'
							: 'left-1/2 -translate-x-1/2 [transition:left_200ms_ease-in-out_150ms,_transform_200ms_ease-in-out_150ms,_color_150ms] '
					)}
				/>
				<span
					class={cn(
						'absolute left-12 text-sm font-medium text-[#344054] transition-[opacity,left] duration-200 data-dark:text-white',
						$showDock ? 'opacity-100' : 'pointer-events-none opacity-0'
					)}
				>
					New Chat
				</span>
			</a>

			<InputText
				oninput={debouncedSearchConvs}
				type="search"
				placeholder="Search chat"
				class={cn(
					'mt-1 h-9 rounded-md bg-[#F2F4F7] pl-8 transition-opacity placeholder:not-italic placeholder:text-[#98A2B3]',
					$showDock ? 'opacity-100' : 'pointer-events-none opacity-0'
				)}
			>
				{#snippet leading()}
					{#if chatState.isLoadingSearch}
						<div class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
							<LoadingSpinner class="h-3" />
						</div>
					{:else}
						<SearchIcon
							class={cn(
								'pointer-events-none absolute left-3 top-1/2 h-[14px] -translate-y-[40%] text-[#667085] transition-opacity',
								$showDock ? 'opacity-100' : 'opacity-0'
							)}
						/>
					{/if}
				{/snippet}
			</InputText>

			<ul
				onscroll={debouncedScrollHandler}
				class="mt-1 flex min-h-52 flex-col overflow-auto transition-opacity {$showDock
					? 'opacity-100'
					: 'opacity-0'}"
			>
				{#each chatState.conversations as conversation (conversation.conversation_id)}
					{#if isEditingTitle == conversation.conversation_id}
						<div
							class="group/item relative flex rounded-lg bg-[#F5F5F5] p-2 text-left transition-colors duration-75 data-dark:bg-[#444951]"
						>
							<form
								onsubmit={(e) => {
									e.preventDefault();
									if (
										!isEditingTitle ||
										(!page.params.project_id && !page.url.searchParams.has('project_id'))
									)
										return;

									const formData = new FormData(e.currentTarget);
									const newTitle = formData.get('edited_title')?.toString();

									if (!newTitle) return;

									chatState.editConversationTitle(
										newTitle,
										isEditingTitle,
										page.params.project_id ?? page.url.searchParams.get('project_id'),
										() => {
											if (chatState.conversation?.conversation_id === isEditingTitle)
												chatState.conversation.title = newTitle ?? '';
											isEditingTitle = null;
											chatState.refetchConversations();
										}
									);
								}}
								class="flex w-full"
							>
								<!-- svelte-ignore a11y_autofocus -->
								<textarea
									autofocus
									rows="3"
									name="edited_title"
									bind:value={editedTitle}
									onblur={(e) => {
										if (e.relatedTarget != saveEditBtn) isEditingTitle = null;
									}}
									onkeydown={(e) => {
										if (e.key === 'Enter') {
											e.preventDefault();
											((e.target as HTMLElement).parentElement as HTMLFormElement).requestSubmit();
										}
									}}
									class="mr-12 w-full resize-none bg-transparent text-sm outline-none"
								></textarea>

								<button
									bind:this={saveEditBtn}
									title="Save title"
									type="submit"
									class="group/button absolute right-7 top-1.5 p-1"
								>
									<CheckIcon
										class="h-4 w-4 stroke-current transition-[stroke] duration-75 group-hover/button:stroke-text/50"
									/>
								</button>
								<button
									title="Cancel edit"
									type="button"
									onclick={() => (isEditingTitle = null)}
									class="group/button absolute right-1 top-1.5 p-1"
								>
									<CloseIcon
										class="h-4 w-4 transition-[stroke] duration-75 [&_path]:stroke-current group-hover/button:[&_path]:stroke-text/50"
									/>
								</button>
							</form>
						</div>
					{:else}
						<a
							data-testid="conversation"
							title={conversation.title || conversation.conversation_id}
							href="/chat/{page.params.project_id ||
								page.url.searchParams.get('project_id')}/{encodeURIComponent(
								conversation.conversation_id
							)}"
							class="group/item relative flex items-center rounded-md p-2 text-left transition-colors duration-75 hover:bg-[#F5F5F5] data-dark:hover:bg-[#444951] {page
								.params.conversation_id === conversation.conversation_id &&
								'data-dark:text-foreground-content bg-[#F5F5F5] data-dark:bg-[#444951]'}"
						>
							<div class="relative flex w-full grow overflow-hidden">
								<span class="line-clamp-1 break-all text-sm">
									{conversation.title || conversation.conversation_id}
								</span>
								<div
									class="absolute right-0 h-full w-[4.5rem] bg-gradient-to-l from-[#F5F5F5] from-75% data-dark:from-[#444951] {page
										.params.conversation_id === conversation.conversation_id
										? 'opacity-100'
										: 'opacity-0'} transition-opacity duration-75 group-hover/item:opacity-100"
								></div>
							</div>

							<div class="absolute right-2 flex items-center">
								<Button
									variant="ghost"
									onclick={(e) => {
										e.preventDefault();
										isEditingTitle = conversation.conversation_id;
										editedTitle = conversation.title;
									}}
									title="Edit conversation ID"
									class="mr-1 h-5 w-5 rounded-full p-0 {page.params.conversation_id ===
									conversation.conversation_id
										? 'opacity-100'
										: 'opacity-0'} transition-opacity duration-75 group-hover/item:opacity-100"
								>
									<EditIcon class="mt-px h-3.5" />
								</Button>

								<Button
									variant="ghost"
									onclick={(e) => {
										e.preventDefault();
										isDeletingConv = conversation.conversation_id;
									}}
									title="Delete conversation"
									class="h-5 w-5 rounded-full p-0 {page.params.conversation_id ===
									conversation.conversation_id
										? 'opacity-100'
										: 'opacity-0'} transition-opacity duration-75 group-hover/item:opacity-100"
								>
									<Trash2 class="h-4 !text-[#F04438]" />
								</Button>
							</div>
						</a>
					{/if}
				{/each}
			</ul>
		</div>

		<hr class="border-[#DDD] data-dark:border-[#454545] md:hidden" />
	</nav>
</div>

<DeleteConvDialog
	bind:isDeletingConv
	deleteCb={() => {
		if (chatState.conversation?.conversation_id === isDeletingConv) {
			goto(
				`/chat?${new URLSearchParams([
					['project_id', page.params.project_id],
					['agent', chatState.conversation.parent_id ?? '']
				])}`
			);
		}

		chatState.refetchConversations();
	}}
/>
