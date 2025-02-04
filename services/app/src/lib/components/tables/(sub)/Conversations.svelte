<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount, tick } from 'svelte';
	import debounce from 'lodash/debounce';
	import autoAnimate from '@formkit/auto-animate';
	import { OverlayScrollbarsComponent } from 'overlayscrollbars-svelte';
	import { browser } from '$app/environment';
	import { beforeNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	// import { activeConversation, pastConversations, type DBConversation } from './conversationsStore';
	import { showRightDock } from '$globalStore';
	import logger from '$lib/logger';
	import type { GenTable, Timestamp } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import InputText from '$lib/components/InputText.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import DeleteIcon from '$lib/icons/DeleteIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

	const timestampsDisplayName: { [key: string]: string } = {
		today: 'Today',
		yesterday: 'Yesterday',
		two_days: 'Two days ago',
		three_days: 'Three days ago',
		last_week: 'Last week',
		last_month: 'Last month',
		older: 'Older'
	};

	let autoAnimateController: ReturnType<typeof autoAnimate>;
	let pastConversations: GenTable[] = [];
	let searchResults: typeof pastConversations = [];

	let isEditingTitle: string | null = null;
	let editedTitle: string;
	let saveEditBtn: HTMLButtonElement;

	let isDeletingConv: string | null = null;

	let fetchConvController: AbortController | null = null;
	let isFilterByAgent = false;
	let isLoadingMoreConversations = false;
	let moreConversationsFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	let searchQuery: string;
	let isNoResults = false;

	async function getPastConversations() {
		const tableData = (await $page.data.table) as
			| {
					error: number;
					message: any;
					data?: undefined;
			  }
			| {
					data: GenTable;
					error?: undefined;
					message?: undefined;
			  };
		if (!tableData.data) return;

		fetchConvController?.abort('Duplicate');
		fetchConvController = new AbortController();
		autoAnimateController?.disable();
		isLoadingMoreConversations = true;

		try {
			const searchParams = new URLSearchParams({
				offset: currentOffset.toString(),
				limit: limit.toString()
			});

			if (isFilterByAgent) {
				searchParams.append('parent_id', tableData.data.parent_id ?? '');
			}

			const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` + searchParams, {
				credentials: 'same-origin',
				signal: fetchConvController?.signal,
				headers: {
					'x-project-id': $page.params.project_id
				}
			});
			currentOffset += limit;

			if (response.status == 200) {
				const moreConversations = await response.json();
				if (moreConversations.items.length) {
					pastConversations = [...pastConversations, ...moreConversations.items];
				} else {
					moreConversationsFinished = true;
				}
			} else {
				const responseBody = await response.json();
				logger.error('CHATTBL_LIST_CONV', responseBody);
				console.error(responseBody.message);
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated' && err !== 'Duplicate') {
				console.error(err);
			}
		}

		isLoadingMoreConversations = false;
		await tick();
		await tick();
		autoAnimateController?.enable();
	}

	onMount(() => {
		$page.data.table.then(() => {
			if (browser) {
				currentOffset = 0;
				moreConversationsFinished = false;
				pastConversations = [];
				getPastConversations();
			}
		});

		return () => {
			fetchConvController?.abort();
			pastConversations = [];
		};
	});

	//* Load more conversations when scrolling down
	const scrollHandler = async (
		instance: NonNullable<ReturnType<OverlayScrollbarsComponent['osInstance']>>,
		e: Event
	) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !isLoadingMoreConversations && !moreConversationsFinished) {
			await getPastConversations();
		}
	};

	let timestamps: Timestamp = {
		today: null,
		yesterday: null,
		two_days: null,
		three_days: null,
		last_week: null,
		last_month: null,
		older: null
	};

	let timestampKeys = Object.keys(timestamps) as Array<keyof Timestamp>;

	$: {
		timestampKeys.forEach((key) => (timestamps[key] = null));
		pastConversations.forEach((conversation, index) => {
			const timeDiff = Date.now() - new Date(conversation.updated_at).getTime();
			if (timeDiff < 24 * 60 * 60 * 1000) {
				if (timestamps.today == null) {
					timestamps.today = index;
				}
			} else if (timeDiff < 2 * 24 * 60 * 60 * 1000) {
				if (timestamps.yesterday == null) {
					timestamps.yesterday = index;
				}
			} else if (timeDiff < 3 * 24 * 60 * 60 * 1000) {
				if (timestamps.two_days == null) {
					timestamps.two_days = index;
				}
			} else if (timeDiff < 4 * 24 * 60 * 60 * 1000) {
				if (timestamps.three_days == null) {
					timestamps.three_days = index;
				}
			} else if (timeDiff < 2 * 7 * 24 * 60 * 60 * 1000) {
				if (timestamps.last_week == null) {
					timestamps.last_week = index;
				}
			} else if (timeDiff < 30 * 24 * 60 * 60 * 1000) {
				if (timestamps.last_month == null) {
					timestamps.last_month = index;
				}
			} else if (timestamps.older == null) {
				timestamps.older = index;
			}
		});
	}

	beforeNavigate(() => (isEditingTitle = null));

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			((e.target as HTMLElement).parentElement as HTMLFormElement).requestSubmit();
		}
	}

	let isLoadingSearch = false;
	const debouncedSearchConv = () => {};
</script>

<span class="flex items-center gap-2 mt-3 text-sm text-[#999999]">Chat history</span>

<div inert={!$showRightDock || null} class="relative mt-1">
	<InputText
		on:input={({ detail: e }) => {
			//@ts-expect-error Generic type
			debouncedSearchConv(e.target?.value ?? '');
		}}
		bind:value={searchQuery}
		type="search"
		placeholder="Search"
		class="pl-8 h-9 placeholder:not-italic placeholder:text-[#98A2B3] bg-[#F2F4F7] rounded-full"
	>
		<svelte:fragment slot="leading">
			{#if isLoadingSearch}
				<div class="absolute top-1/2 left-3 -translate-y-1/2 pointer-events-none">
					<LoadingSpinner class="h-3" />
				</div>
			{:else}
				<SearchIcon
					class="absolute top-1/2 left-3 -translate-y-1/2 h-3 text-[#667085] pointer-events-none"
				/>
			{/if}
		</svelte:fragment>
	</InputText>
</div>

<div class="flex items-center gap-2 mt-2 text-sm">
	<Switch
		id="conv-list-filter"
		name="conv-list-filter"
		bind:checked={isFilterByAgent}
		onCheckedChange={() => {
			currentOffset = 0;
			moreConversationsFinished = false;
			pastConversations = [];
			getPastConversations();
		}}
		class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
	/>
	<label for="conv-list-filter" class="text-[#475467]">Filter by agent</label>
</div>

{#if searchResults.length || isNoResults}
	{#if isNoResults}
		<div class="flex items-center justify-center h-20">
			<span class="text-foreground-content/60">No results found</span>
		</div>
	{:else}
		<span class="px-6 py-2 pt-4 text-sm">
			Search results:
			<span class="italic">{searchQuery}</span>
		</span>

		<hr class="w-[calc(100%_+_1.5rem)] -translate-x-3 border-[#454545]" />
	{/if}
{/if}

<OverlayScrollbarsComponent
	inert={!$showRightDock || null}
	defer
	data-testid="conversations"
	events={{ scroll: debounce(scrollHandler, 300) }}
	on:osInitialized={(e) => {
		autoAnimateController = autoAnimate(e.detail[0].elements().viewport);
	}}
	class="grow flex flex-col my-3 rounded-md overflow-auto os-dark"
>
	{#each !searchResults.length && !isNoResults ? pastConversations : searchResults as conversation, index (conversation.id)}
		{#if !searchResults.length && !isNoResults}
			{#each timestampKeys as time (time)}
				{#if timestamps[time] == index}
					<div class="my-2">
						<span class="text-sm text-[#999] font-semibold">
							{timestampsDisplayName[time]}
						</span>
					</div>
				{/if}
			{/each}
		{/if}
		{#if isEditingTitle === conversation.id}
			<div
				class="relative flex my-2 px-3 py-2 bg-[#F5F5F5] data-dark:bg-[#444951] text-left transition-colors duration-75 rounded-lg group/item"
			>
				<!-- on:submit|preventDefault={saveTitle} -->
				<form class="flex w-full">
					<!-- svelte-ignore a11y-autofocus -->
					<textarea
						autofocus
						rows="3"
						name="edited-title"
						bind:value={editedTitle}
						on:keydown={interceptSubmit}
						on:blur={(e) => {
							if (e.relatedTarget != saveEditBtn) isEditingTitle = null;
						}}
						class="mr-12 w-full bg-transparent resize-none outline-none text-sm"
					/>

					<button
						bind:this={saveEditBtn}
						title="Save title"
						type="submit"
						class="absolute top-1.5 right-7 p-1 group/button"
					>
						<CheckIcon
							class="h-5 w-5 stroke-current group-hover/button:stroke-text/50 transition-[stroke] duration-75"
						/>
					</button>
					<button
						title="Cancel edit"
						type="button"
						class="absolute top-1.5 right-1 p-1 group/button"
					>
						<CloseIcon
							class="h-5 w-5 [&_path]:stroke-current group-hover/button:[&_path]:stroke-text/50 transition-[stroke] duration-75"
						/>
					</button>
				</form>
			</div>
		{:else}
			<a
				data-testid="conversation"
				title={conversation.id}
				href="/project/{$page.params.project_id}/chat-table/{conversation.id}"
				class="relative flex items-center p-2 text-left {$page.params.table_id ===
					conversation.id &&
					'data-dark:text-foreground-content bg-[#F5F5F5] data-dark:bg-[#444951]'} hover:bg-[#F5F5F5] data-dark:hover:bg-[#444951] transition-colors duration-75 rounded-lg group/item"
			>
				<ChatTableIcon class="flex-[0_0_auto] h-[18px] mr-2" />

				<div class="relative flex grow w-full overflow-hidden">
					<span class="text-sm line-clamp-1 break-all">
						{conversation.id}
					</span>
					<div
						class="absolute right-0 h-full w-10 bg-gradient-to-l from-[#F5F5F5] data-dark:from-[#444951] from-75% {$page
							.params.table_id === conversation.id
							? 'opacity-100'
							: 'opacity-0'} group-hover/item:opacity-100 transition-opacity duration-75"
					/>
				</div>

				<Button
					variant="ghost"
					on:click={() => {}}
					title="Edit conversation ID"
					class="mr-1 p-0 h-5 w-5 rounded-full {$page.params.table_id === conversation.id
						? 'visible'
						: 'invisible'} group-hover/item:visible"
				>
					<EditIcon class="h-4" />
				</Button>

				<Button
					variant="ghost"
					on:click={(e) => {
						e.preventDefault();
						isDeletingConv = conversation.id;
					}}
					title="Delete conversation"
					class="p-0 h-5 w-5 rounded-full invisible {$page.params.table_id === conversation.id
						? 'visible'
						: 'invisible'} group-hover/item:visible"
				>
					<DeleteIcon class="h-6" />
				</Button>
			</a>
		{/if}
	{/each}
	{#if isLoadingMoreConversations}
		<div class="flex items-center justify-center mx-auto p-4">
			<LoadingSpinner class="h-5 w-5 text-secondary" />
		</div>
	{/if}
</OverlayScrollbarsComponent>
