<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import debounce from 'lodash/debounce';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { page } from '$app/state';
	import { cTableSort as sortOptions } from '$globalStore';
	import { pastChatAgents } from '$lib/components/tables/tablesState.svelte';
	import { agentColors } from '$lib/constants';
	import logger from '$lib/logger';

	import { AddAgentDialog, AddConversationDialog } from './(dialogs)';
	import { ExportTableButton } from '../(components)';
	import { DeleteTableDialog, ImportTableDialog, RenameTableDialog } from '../(dialogs)';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import SorterSelect from '$lib/components/preset/SorterSelect.svelte';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';
	import SortAlphabetIcon from '$lib/icons/SortAlphabetIcon.svelte';
	import SortByIcon from '$lib/icons/SortByIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	let { data } = $props();
	let { user } = $derived(data);

	const bigScreen = new MediaQuery('min-width: 1024px');
	let componentWidth: number = $state(0);
	let supportsContainerQuery = $state(true);
	let selectingFilterAgent = $state(true);

	let filterByAgent = $state('_chat_');
	let fetchFilteredConvController: AbortController | null = null;
	let isLoadingFilteredConv = $state(false);
	let isLoadingMoreFilteredConv = $state(false);
	let moreFilteredConvFinished = false;
	let currentOffsetFilteredConv = 0;
	const limitFilteredConv = 100;
	let filteredConversations: typeof $pastChatAgents = $state([]);
	const sortableFields = [
		{ id: 'id', title: 'Name', Icon: SortAlphabetIcon },
		{ id: 'updated_at', title: 'Date modified', Icon: SortByIcon }
	];

	const filteredConvColorMap = new Map<string, (typeof agentColors)[number]>();
	const mapAgentColors = () => {
		filteredConversations.forEach((conv) => {
			if (conv.parent_id && !filteredConvColorMap.get(conv.parent_id))
				filteredConvColorMap.set(
					conv.parent_id,
					agentColors[filteredConvColorMap.size % agentColors.length]
				);
		});
	};

	let fetchAgentsController: AbortController | null = null;
	let loadingAgentsError: { status: number; message: string; org_id?: string } | null =
		$state(null);
	let isLoadingCAgents = $state(true);
	let isLoadingMoreCAgents = $state(false);
	let moreCAgentsFinished = false;
	let currentOffsetAgents = 0;
	const limitAgents = 100;

	let searchQuery = $state('');
	let searchController: AbortController | null = null;
	let isLoadingSearch = $state(false);

	let isAddingAgent = $state(false);
	let isAddingConversation = $state(false);
	let isEditingTableID: string | null = $state(null);
	let isDeletingTable: string | null = $state(null);
	let isImportingTable: File | null = $state(null);

	onMount(() => {
		getChatAgents();
		getConvFilterByAgent(filterByAgent);

		if (!CSS.supports('container-type', 'inline-size')) {
			supportsContainerQuery = false;
		}

		return () => {
			fetchFilteredConvController?.abort('Navigated');
			filteredConversations = [];

			fetchAgentsController?.abort('Navigated');
			$pastChatAgents = [];
		};
	});

	async function getChatAgents() {
		if (!isLoadingCAgents) {
			isLoadingMoreCAgents = true;
		}

		fetchAgentsController?.abort('Duplicate');
		fetchAgentsController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/list?` +
					new URLSearchParams({
						offset: currentOffsetAgents.toString(),
						limit: limitAgents.toString(),
						parent_id: '_agent_'
					}),
				{
					credentials: 'same-origin',
					signal: fetchAgentsController.signal
				}
			);
			currentOffsetAgents += limitAgents;

			if (response.status == 200) {
				const moreChatAgents = await response.json();
				if (moreChatAgents.items.length) {
					$pastChatAgents = [...$pastChatAgents, ...moreChatAgents.items];
				} else {
					//* Finished loading oldest conversation
					moreCAgentsFinished = true;
				}
			} else {
				const responseBody = await response.json();
				if (response.status !== 404) {
					logger.error('CHATTBL_LIST_AGENT', responseBody);
				}
				console.error(responseBody);
				toast.error('Failed to fetch chat agents', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
				loadingAgentsError = {
					status: response.status,
					message: responseBody.message,
					org_id: responseBody.org_id
				};
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated' && err !== 'Duplicate') {
				console.error(err);
			}
		}

		isLoadingCAgents = false;
		isLoadingMoreCAgents = false;
	}

	async function getConvFilterByAgent(agentId: string, showFiltered = false) {
		if (agentId === filterByAgent && filteredConversations.length !== 0) {
			isLoadingMoreFilteredConv = true;
		} else {
			isLoadingFilteredConv = true;
			filteredConversations = [];
			currentOffsetFilteredConv = 0;
			moreFilteredConvFinished = false;
			filterByAgent = agentId;
		}

		if (showFiltered) selectingFilterAgent = false;

		fetchFilteredConvController?.abort('Duplicate');
		fetchFilteredConvController = new AbortController();

		try {
			const searchParams = {
				offset: currentOffsetFilteredConv.toString(),
				limit: limitFilteredConv.toString(),
				order_by: $sortOptions.orderBy,
				order_ascending: $sortOptions.order === 'asc' ? 'true' : 'false',
				parent_id: filterByAgent,
				search_query: searchQuery.trim()
			} as Record<string, string>;

			if (searchParams.search_query === '') {
				delete searchParams.search_query;
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/list?` + new URLSearchParams(searchParams),
				{
					credentials: 'same-origin',
					signal: fetchFilteredConvController.signal
				}
			);
			currentOffsetFilteredConv += limitFilteredConv;

			const responseBody = await response.json();
			if (response.ok) {
				if (responseBody.items.length) {
					filteredConversations = [...filteredConversations, ...responseBody.items];
				} else {
					//* Finished loading oldest conversation
					moreFilteredConvFinished = true;
				}
			} else {
				if (response.status !== 404) {
					logger.error('CHATTBL_LIST_TBL', responseBody);
				}
				console.error(responseBody);
				toast.error('Failed to fetch filtered conversations', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}

			isLoadingFilteredConv = false;
			isLoadingMoreFilteredConv = false;
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated' && err !== 'Duplicate') {
				console.error(err);
				isLoadingFilteredConv = false;
				isLoadingMoreFilteredConv = false;
			}
		}
	}

	async function refetchTables() {
		if (searchQuery) {
			await handleSearchTables(searchQuery);
		} else {
			searchController?.abort('Duplicate');

			await Promise.all([
				(async () => {
					$pastChatAgents = [];
					currentOffsetAgents = 0;
					moreCAgentsFinished = false;
					await getChatAgents();
				})(),
				(async () => {
					filteredConversations = [];
					currentOffsetFilteredConv = 0;
					moreFilteredConvFinished = false;
					await getConvFilterByAgent(filterByAgent);
				})()
			]);

			isLoadingSearch = false;
		}
	}

	async function handleSearchTables(q: string) {
		isLoadingSearch = true;

		if (!searchQuery) return refetchTables();

		searchController?.abort('Duplicate');
		searchController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/list?${new URLSearchParams({
					limit: limitFilteredConv.toString(),
					order_by: $sortOptions.orderBy,
					order_ascending: $sortOptions.order === 'asc' ? 'true' : 'false',
					parent_id: filterByAgent,
					search_query: q
				})}`,
				{
					signal: searchController.signal
				}
			);
			currentOffsetFilteredConv = limitFilteredConv;
			moreFilteredConvFinished = false;

			const responseBody = await response.json();
			if (response.ok) {
				filteredConversations = responseBody.items;
			} else {
				logger.error('CHATTBL_TBL_SEARCHTBL', responseBody);
				console.error(responseBody);
				toast.error('Failed to search tables', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}
			isLoadingSearch = false;
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
				isLoadingSearch = false;
			}
		}
	}
	const debouncedSearchTables = debounce(handleSearchTables, 300);

	async function handleFilesUpload(
		e: Event & {
			currentTarget: EventTarget & HTMLInputElement;
		},
		files: File[]
	) {
		e.currentTarget.value = '';

		if (files.length === 0) return;
		if (files.length > 1) {
			alert('Cannot import multiple tables at the same time');
			return;
		}

		const allowedFiletypes = ['.parquet'];
		if (
			files.some(
				(file) => !allowedFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(`Files must be of type: ${allowedFiletypes.join(', ').replaceAll('.', '')}`);
			return;
		}

		isImportingTable = files[0];
	}

	const scrollHandler = async (e: Event, type: 'agent' | 'filtered') => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (offset < LOAD_THRESHOLD && !isLoadingCAgents) {
			switch (type) {
				case 'agent': {
					if (!moreCAgentsFinished) {
						await getChatAgents();
					}
					break;
				}
				case 'filtered': {
					if (!moreFilteredConvFinished) {
						await getConvFilterByAgent(filterByAgent);
					}
					break;
				}
				default:
					break;
			}
		}
	};

	$effect(() => {
		filteredConversations;
		mapAgentColors();
	});
</script>

<svelte:head>
	<title>Chat Table</title>
</svelte:head>

<div bind:offsetWidth={componentWidth} class="flex grow flex-col gap-3 overflow-hidden @container">
	{#if !loadingAgentsError}
		<div
			class="grid h-1 w-[200%] grow grid-cols-2 @2xl:w-auto @2xl:grid-cols-[minmax(300px,3fr)_minmax(0,10fr)] supports-[not(container-type:inline-size)]:lg:w-auto supports-[not(container-type:inline-size)]:lg:grid-cols-[minmax(300px,3fr)_minmax(0,10fr)] {selectingFilterAgent
				? 'translate-x-0'
				: '-translate-x-[50%] @2xl:translate-x-0 supports-[not(container-type:inline-size)]:lg:translate-x-0'} transition-transform"
		>
			<div
				inert={(supportsContainerQuery
					? componentWidth !== undefined && componentWidth < 672
					: !bigScreen.current) && !selectingFilterAgent}
				data-testid="agents-list"
				class="my-2.5 ml-7 mr-7 flex min-h-0 flex-col gap-2 rounded-lg border border-[#E5E5E5] bg-white px-2 py-3 @2xl:my-4 @2xl:mr-1.5 data-dark:border-[#484C55] data-dark:bg-[#303338] supports-[not(container-type:inline-size)]:lg:my-4 supports-[not(container-type:inline-size)]:lg:mr-1.5"
			>
				<div class="flex items-center justify-between">
					<h3 class="ml-1 text-[#344054]">Agents</h3>

					<Button
						onclick={() => (isAddingAgent = true)}
						variant="ghost"
						title="New agent"
						class="aspect-square h-7 w-7 p-0"
					>
						<AddIcon class="h-3.5 w-3.5 text-[#667085]" />
					</Button>
				</div>

				<div
					onscroll={debounce((e) => scrollHandler(e, 'agent'), 300)}
					class="flex grow flex-col gap-1 overflow-auto"
				>
					{#if isLoadingCAgents}
						{#each Array(6) as _}
							<Skeleton
								class="flex h-9 w-full flex-[0_0_auto] flex-col rounded bg-black/[0.09] data-dark:bg-white/[0.1]"
							/>
						{/each}
					{:else}
						<button
							onclick={() => {
								if (filterByAgent !== '_chat_') {
									getConvFilterByAgent('_chat_', true);
								} else {
									selectingFilterAgent = false;
								}
							}}
							title="All agents"
							class="flex w-full flex-[0_0_auto] gap-1 px-2 py-2 text-start text-sm {filterByAgent ===
							'_chat_'
								? 'bg-[#FFEFF2] text-[#950048]'
								: 'text-[#667085] hover:bg-[#F2F4F7]'} rounded-lg transition-colors"
						>
							<!-- <ChatAgentIcon class="h-5 flex-[0_0_auto]" /> -->
							<span class="line-clamp-1 break-all">All agents</span>
							{#if filterByAgent === '_chat_'}
								<CheckIcon class="ml-auto h-4 flex-[0_0_auto] self-center text-[#950048]" />
							{/if}
						</button>

						{#each $pastChatAgents as chatTable (chatTable.id)}
							<button
								onclick={() => {
									if (filterByAgent !== chatTable.id) {
										getConvFilterByAgent(chatTable.id, true);
									} else {
										selectingFilterAgent = false;
									}
								}}
								title={chatTable.id}
								class="flex w-full flex-[0_0_auto] gap-1 px-2 py-2 text-sm {filterByAgent ===
								chatTable.id
									? 'bg-[#FFEFF2] text-[#950048]'
									: 'text-[#667085] hover:bg-[#F2F4F7]'} rounded-lg transition-colors"
							>
								<!-- <ChatAgentIcon class="h-5 flex-[0_0_auto]" /> -->
								<span class="line-clamp-1 break-all">{chatTable.id}</span>
								{#if filterByAgent === chatTable.id}
									<CheckIcon class="ml-auto h-4 self-center text-[#950048]" />
								{/if}
							</button>
						{/each}

						{#if isLoadingMoreCAgents}
							<div class="mx-auto flex items-center justify-center p-2">
								<LoadingSpinner class="h-5 w-5 text-secondary" />
							</div>
						{/if}
					{/if}
				</div>
			</div>

			<div
				inert={(supportsContainerQuery
					? componentWidth !== undefined && componentWidth < 672
					: !bigScreen.current) && selectingFilterAgent}
				data-testid="conv-list"
				onscroll={debounce((e) => scrollHandler(e, 'filtered'), 300)}
				class="flex flex-col gap-1 py-2.5 pl-6 pr-6 @2xl:py-4 @2xl:pl-0.5 supports-[not(container-type:inline-size)]:lg:py-4 supports-[not(container-type:inline-size)]:lg:pl-0.5"
			>
				{#if filterByAgent}
					<div class="mx-1 flex items-center gap-2">
						<Button
							variant="ghost"
							onclick={() => (selectingFilterAgent = true)}
							class="group relative flex aspect-square p-0 @2xl:hidden supports-[not(container-type:inline-size)]:lg:hidden"
						>
							<ArrowLeft size={20} class="text-[#344054]" />

							<Tooltip
								arrowSize={5}
								class="left-[calc(100%+8px)] top-1/2 z-20 -translate-y-1/2 opacity-0 transition-opacity after:left-0 after:top-1/2 after:-translate-x-[100%] after:-translate-y-1/2 after:rotate-90 group-hover:opacity-100"
							>
								Select agent
							</Tooltip>
						</Button>

						<a
							title={filterByAgent}
							href="/project/{page.params.project_id}/chat-table/{encodeURIComponent(
								filterByAgent
							)}"
							class="relative flex w-full items-center justify-between rounded-md border border-[#E5E5E5] bg-white px-2 py-[7px] @2xl:rounded-lg @2xl:px-3 @2xl:py-3 data-dark:border-[#484C55] data-dark:bg-[#303338] supports-[not(container-type:inline-size)]:lg:rounded-xl supports-[not(container-type:inline-size)]:lg:px-4 supports-[not(container-type:inline-size)]:lg:py-3 {filterByAgent ===
							'_chat_'
								? 'pointer-events-none'
								: ''}"
						>
							<div class="flex items-center gap-2">
								<div
									class="relative h-6 w-6 flex-[0_0_auto] overflow-hidden rounded-sm bg-[#F2F4F7]"
								>
									<ChatAgentIcon
										class="absolute -bottom-[3px] left-1/2 aspect-square h-[26px] -translate-x-1/2 text-[#475467]"
									/>
								</div>
								<span
									class="line-clamp-1 text-sm font-medium text-[#344054] @2xl:text-base supports-[not(container-type:inline-size)]:lg:text-base"
								>
									{filterByAgent === '_chat_' ? 'All agents' : filterByAgent}
								</span>
							</div>

							{#if filterByAgent && filterByAgent !== '_chat_'}
								<DropdownMenu.Root>
									<DropdownMenu.Trigger>
										{#snippet child({ props })}
											<Button
												{...props}
												variant="ghost"
												onclick={(e) => e.preventDefault()}
												title="Agent settings"
												class="absolute right-1.5 aspect-square h-7 w-7 flex-[0_0_auto] p-0 @2xl:right-3 supports-[not(container-type:inline-size)]:lg:right-4"
											>
												<MoreVertIcon class="h-[18px] w-[18px]" />
											</Button>
										{/snippet}
									</DropdownMenu.Trigger>
									<DropdownMenu.Content align="end">
										<DropdownMenu.Group>
											<DropdownMenu.Item
												onclick={() => (isEditingTableID = filterByAgent)}
												class="text-[#344054] data-[highlighted]:text-[#344054]"
											>
												<EditIcon class="mr-2 h-3.5 w-3.5" />
												<span>Rename agent</span>
											</DropdownMenu.Item>
											<ExportTableButton tableId={filterByAgent} tableType="chat">
												{#snippet children({ handleExportTable })}
													<DropdownMenu.Item
														onclick={handleExportTable}
														class="text-[#344054] data-[highlighted]:text-[#344054]"
													>
														<ExportIcon class="mr-2 h-3.5 w-3.5" />
														<span>Export agent</span>
													</DropdownMenu.Item>
												{/snippet}
											</ExportTableButton>
											<DropdownMenu.Separator />
											<DropdownMenu.Item
												onclick={() => (isDeletingTable = filterByAgent)}
												class="text-destructive data-[highlighted]:text-destructive"
											>
												<Trash_2 class="mr-2 h-3.5 w-3.5" />
												<span>Delete agent</span>
											</DropdownMenu.Item>
										</DropdownMenu.Group>
									</DropdownMenu.Content>
								</DropdownMenu.Root>
							{/if}
						</a>
					</div>

					<div
						class="grid h-min min-w-0 grid-cols-[12rem_min-content_minmax(0,auto)_min-content_min-content] items-center gap-1 overflow-auto px-1 [scrollbar-gutter:stable] sm:overflow-visible sm:pt-1"
					>
						<SearchBar
							bind:searchQuery
							{isLoadingSearch}
							debouncedSearch={debouncedSearchTables}
							label="Search table"
							placeholder="Search table"
							class="w-[12rem]"
						/>

						<SorterSelect bind:sortOptions={$sortOptions} {sortableFields} {refetchTables} />

						<div></div>

						<Button
							variant="action"
							title="Create table"
							onclick={() => (isAddingConversation = true)}
							class="flex aspect-square h-8 flex-[0_0_auto] items-center justify-center gap-1.5 px-2 py-2 text-xs xs:aspect-auto xs:h-9 xs:px-3 sm:text-sm"
						>
							<AddIcon class="h-3.5 w-3.5" />
							<!-- <span class="hidden xs:block">Create table</span> -->
						</Button>

						<Button
							variant="action"
							title="Import table"
							onclick={(e) => e.currentTarget.querySelector('input')?.click()}
							class="flex aspect-square h-8 w-8 flex-[0_0_auto] items-center gap-2 p-0 xs:h-9 xs:w-9 md:aspect-auto"
						>
							<ImportIcon class="h-3.5 w-3.5" />

							<!-- <span class="hidden md:block">Import table</span> -->

							<input
								tabindex="-1"
								id="action-tbl-import"
								type="file"
								accept=".parquet"
								onchange={(e) => {
									e.preventDefault();
									handleFilesUpload(e, [...(e.currentTarget.files ?? [])]);
								}}
								multiple={false}
								class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
							/>
						</Button>
					</div>

					<div
						onscroll={debounce((e) => scrollHandler(e, 'filtered'), 300)}
						style="grid-auto-rows: 120px;"
						class="grid h-1 grow grid-flow-row grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] gap-3 overflow-auto px-1 pt-1 [scrollbar-gutter:stable]"
					>
						{#if isLoadingFilteredConv}
							<div class="col-span-full mx-auto flex items-center justify-center p-4">
								<LoadingSpinner class="h-5 w-5 text-secondary" />
							</div>
						{:else}
							{#each filteredConversations as chatTable}
								<a
									href="/project/{page.params.project_id}/chat-table/{encodeURIComponent(
										chatTable.id
									)}"
									title={chatTable.id}
									class="flex flex-col rounded-lg border border-[#E4E7EC] bg-white transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-float data-dark:border-[#333] data-dark:bg-[#42464E]"
								>
									<div class="flex w-full grow items-start justify-between p-3">
										<div class="flex items-start gap-1.5">
											<ChatTableIcon class="h-5 w-5 flex-[0_0_auto] text-[#475467]" />
											<span class="line-clamp-2 break-all text-sm text-[#344054]">
												{chatTable.id}
											</span>
										</div>

										<DropdownMenu.Root>
											<DropdownMenu.Trigger>
												{#snippet child({ props })}
													<Button
														{...props}
														variant="ghost"
														onclick={(e) => e.preventDefault()}
														title="Table settings"
														class="aspect-square h-7 w-7 flex-[0_0_auto] -translate-y-1.5 translate-x-1.5 p-0"
													>
														<MoreVertIcon class="h-[18px] w-[18px]" />
													</Button>
												{/snippet}
											</DropdownMenu.Trigger>
											<DropdownMenu.Content align="end">
												<DropdownMenu.Group>
													<DropdownMenu.Item
														onclick={() => (isEditingTableID = chatTable.id)}
														class="text-[#344054] data-[highlighted]:text-[#344054]"
													>
														<EditIcon class="mr-2 h-3.5 w-3.5" />
														<span>Rename table</span>
													</DropdownMenu.Item>
													<ExportTableButton tableId={chatTable.id} tableType="chat">
														{#snippet children({ handleExportTable })}
															<DropdownMenu.Item
																onclick={handleExportTable}
																class="text-[#344054] data-[highlighted]:text-[#344054]"
															>
																<ExportIcon class="mr-2 h-3.5 w-3.5" />
																<span>Export table</span>
															</DropdownMenu.Item>
														{/snippet}
													</ExportTableButton>
													<DropdownMenu.Separator />
													<DropdownMenu.Item
														onclick={() => (isDeletingTable = chatTable.id)}
														class="text-destructive data-[highlighted]:text-destructive"
													>
														<Trash_2 class="mr-2 h-3.5 w-3.5" />
														<span>Delete table</span>
													</DropdownMenu.Item>
												</DropdownMenu.Group>
											</DropdownMenu.Content>
										</DropdownMenu.Root>
									</div>

									<div class="flex items-center justify-between px-3 py-2">
										<span
											title={new Date(chatTable.updated_at).toLocaleString(undefined, {
												month: 'long',
												day: 'numeric',
												year: 'numeric'
											})}
											class="line-clamp-1 text-xs font-medium text-[#98A2B3] data-dark:text-[#C9C9C9]"
										>
											Last updated
											<span class="text-[#475467]">
												{new Date(chatTable.updated_at).toLocaleString(undefined, {
													month: 'long',
													day: 'numeric',
													year: 'numeric'
												})}
											</span>
										</span>

										{#if filterByAgent === '_chat_' && chatTable.parent_id}
											{@const mappedColors = filteredConvColorMap.get(chatTable.parent_id)}
											<span
												style="background-color: {mappedColors
													? mappedColors.bg
													: '#E3F2FD'}; color: {mappedColors ? mappedColors.text : '#0295FF'};"
												class="w-min select-none whitespace-nowrap rounded-[0.1875rem] px-1 py-0.5 text-xs font-medium"
											>
												{chatTable.parent_id}
											</span>
										{/if}
									</div>
								</a>
							{/each}

							{#if isLoadingMoreFilteredConv}
								<div class="mx-auto flex items-center justify-center p-4">
									<LoadingSpinner class="h-5 w-5 text-secondary" />
								</div>
							{/if}
						{/if}
					</div>
				{:else}
					<span class="my-auto self-center font-medium text-[#999]">
						Select agent to filter conversations
					</span>
				{/if}
			</div>
		</div>
	{:else if loadingAgentsError.status === 404 && loadingAgentsError.org_id && user?.org_memberships?.find((org) => org.organization_id === loadingAgentsError?.org_id)}
		{@const projectOrg = user?.organizations.find((org) => org.id === loadingAgentsError?.org_id)}
		<FoundProjectOrgSwitcher {projectOrg} />
	{:else}
		<div class="mx-4 my-0 flex h-full items-center justify-center">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{loadingAgentsError.status}
			</span>
			<div
				class="ml-4 flex min-h-10 items-center border-l border-[#ccc] pl-4 data-dark:border-[#666]"
			>
				<h1>{loadingAgentsError.message}</h1>
			</div>
		</div>
	{/if}
</div>

<AddAgentDialog bind:isAddingAgent />
<AddConversationDialog bind:isAddingConversation bind:filteredConversations {filterByAgent} />
<RenameTableDialog
	tableType="chat"
	bind:isEditingTableID
	editedCb={(success, tableID) => {
		if (success && tableID) {
			filteredConversations = [];
			getConvFilterByAgent(isEditingTableID === filterByAgent ? tableID : filterByAgent);
		}
	}}
/>
<DeleteTableDialog
	tableType="chat"
	bind:isDeletingTable
	deletedCb={(success, deletedTableID) => {
		if (success) {
			if ($pastChatAgents.find((t) => t.id === deletedTableID)) getConvFilterByAgent('_chat_');
			else if (filteredConversations.find((t) => t.id === deletedTableID))
				filteredConversations = filteredConversations.filter((t) => t.id !== deletedTableID);
		}
	}}
/>
<ImportTableDialog tableType="chat" bind:isImportingTable {refetchTables} />
