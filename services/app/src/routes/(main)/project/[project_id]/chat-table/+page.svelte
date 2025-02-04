<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import ArrowLeft from 'lucide-svelte/icons/arrow-left';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { page } from '$app/stores';
	import { cTableSort as sortOptions } from '$globalStore';
	import { pastChatAgents } from '$lib/components/tables/tablesStore';
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

	export let data;
	$: ({ userData } = data);

	let windowWidth: number;
	let componentWidth: number;
	let supportsContainerQuery = true;
	let selectingFilterAgent = true;

	let filterByAgent = '_chat_';
	let fetchFilteredConvController: AbortController | null = null;
	let isLoadingFilteredConv = false;
	let isLoadingMoreFilteredConv = false;
	let moreFilteredConvFinished = false;
	let currentOffsetFilteredConv = 0;
	const limitFilteredConv = 100;
	let filteredConversations: typeof $pastChatAgents = [];
	const sortableFields = [
		{ id: 'id', title: 'Name', Icon: SortAlphabetIcon },
		{ id: 'updated_at', title: 'Date modified', Icon: SortByIcon }
	];

	const filteredConvColorMap = new Map<string, (typeof agentColors)[number]>();
	$: filteredConversations, mapAgentColors();
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
	let loadingAgentsError: { status: number; message: string; org_id?: string } | null = null;
	let isLoadingCAgents = true;
	let isLoadingMoreCAgents = false;
	let moreCAgentsFinished = false;
	let currentOffsetAgents = 0;
	const limitAgents = 100;

	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let isAddingAgent = false;
	let isAddingConversation = false;
	let isEditingTableID: string | null = null;
	let isDeletingTable: string | null = null;
	let isImportingTable: File | null = null;

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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` +
					new URLSearchParams({
						offset: currentOffsetAgents.toString(),
						limit: limitAgents.toString(),
						parent_id: '_agent_'
					}),
				{
					credentials: 'same-origin',
					signal: fetchAgentsController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
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
					description: CustomToastDesc,
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
				order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
				parent_id: filterByAgent,
				search_query: searchQuery.trim()
			} as Record<string, string>;

			if (searchParams.search_query === '') {
				delete searchParams.search_query;
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?` + new URLSearchParams(searchParams),
				{
					credentials: 'same-origin',
					signal: fetchFilteredConvController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
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
					description: CustomToastDesc,
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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat?${new URLSearchParams({
					limit: limitFilteredConv.toString(),
					order_by: $sortOptions.orderBy,
					order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
					parent_id: filterByAgent,
					search_query: q
				})}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
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
					description: CustomToastDesc,
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
			files.some((file) => !allowedFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase()))
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
</script>

<svelte:head>
	<title>Chat Table</title>
</svelte:head>

<svelte:window bind:innerWidth={windowWidth} />

<div bind:offsetWidth={componentWidth} class="@container grow flex flex-col gap-3 overflow-hidden">
	{#if !loadingAgentsError}
		<div
			class="grow grid grid-cols-2 w-[200%] @2xl:w-auto supports-[not(container-type:inline-size)]:lg:w-auto @2xl:grid-cols-[minmax(300px,3fr)_minmax(0,10fr)] supports-[not(container-type:inline-size)]:lg:grid-cols-[minmax(300px,3fr)_minmax(0,10fr)] h-1 {selectingFilterAgent
				? 'translate-x-0'
				: '-translate-x-[50%] @2xl:translate-x-0 supports-[not(container-type:inline-size)]:lg:translate-x-0'} transition-transform"
		>
			<div
				inert={(supportsContainerQuery
					? componentWidth !== undefined && componentWidth < 672
					: windowWidth !== undefined && windowWidth < 1024) && !selectingFilterAgent}
				data-testid="agents-list"
				class="flex flex-col gap-2 my-2.5 @2xl:my-4 supports-[not(container-type:inline-size)]:lg:my-4 ml-7 mr-7 @2xl:mr-1.5 supports-[not(container-type:inline-size)]:lg:mr-1.5 px-2 py-3 min-h-0 bg-white data-dark:bg-[#303338] border border-[#E5E5E5] data-dark:border-[#484C55] rounded-lg"
			>
				<div class="flex items-center justify-between">
					<h3 class="ml-1">Agents</h3>

					<Button
						on:click={() => (isAddingAgent = true)}
						variant="ghost"
						title="New agent"
						class="p-0 h-7 w-7 aspect-square"
					>
						<AddIcon class="h-3.5 w-3.5 text-[#667085]" />
					</Button>
				</div>

				<div
					on:scroll={debounce((e) => scrollHandler(e, 'agent'), 300)}
					class="grow flex flex-col gap-1 overflow-auto"
				>
					{#if isLoadingCAgents}
						{#each Array(6) as _}
							<Skeleton
								class="flex-[0_0_auto] flex flex-col h-9 w-full bg-black/[0.09] data-dark:bg-white/[0.1] rounded"
							/>
						{/each}
					{:else}
						<button
							on:click={() => {
								if (filterByAgent !== '_chat_') {
									getConvFilterByAgent('_chat_', true);
								} else {
									selectingFilterAgent = false;
								}
							}}
							title="All agents"
							class="flex-[0_0_auto] flex gap-1 px-2 py-2 w-full text-sm text-start {filterByAgent ===
							'_chat_'
								? 'text-[#0295FF] bg-[#E3F2FD]'
								: 'text-[#667085] hover:bg-[#F2F4F7]'} rounded transition-colors"
						>
							<ChatAgentIcon class="flex-[0_0_auto] h-5" />
							<span class="line-clamp-1 break-all">All agents</span>
							{#if filterByAgent === '_chat_'}
								<CheckIcon class="flex-[0_0_auto] self-center ml-auto h-4 text-[#333]" />
							{/if}
						</button>

						{#each $pastChatAgents as chatTable (chatTable.id)}
							<button
								on:click={() => {
									if (filterByAgent !== chatTable.id) {
										getConvFilterByAgent(chatTable.id, true);
									} else {
										selectingFilterAgent = false;
									}
								}}
								title={chatTable.id}
								class="flex-[0_0_auto] flex gap-1 px-2 py-2 w-full text-sm {filterByAgent ===
								chatTable.id
									? 'text-[#0295FF] bg-[#E3F2FD]'
									: 'text-[#667085] hover:bg-[#F2F4F7]'} rounded transition-colors"
							>
								<ChatAgentIcon class="flex-[0_0_auto] h-5" />
								<span class="line-clamp-1 break-all">{chatTable.id}</span>
								{#if filterByAgent === chatTable.id}
									<CheckIcon class="self-center ml-auto h-4 text-[#333]" />
								{/if}
							</button>
						{/each}

						{#if isLoadingMoreCAgents}
							<div class="flex items-center justify-center mx-auto p-2">
								<LoadingSpinner class="h-5 w-5 text-secondary" />
							</div>
						{/if}
					{/if}
				</div>
			</div>

			<div
				inert={(supportsContainerQuery
					? componentWidth !== undefined && componentWidth < 672
					: windowWidth !== undefined && windowWidth < 1024) && selectingFilterAgent}
				data-testid="conv-list"
				on:scroll={debounce((e) => scrollHandler(e, 'filtered'), 300)}
				class="flex flex-col gap-1 pl-6 @2xl:pl-0.5 supports-[not(container-type:inline-size)]:lg:pl-0.5 pr-6 py-2.5 @2xl:py-4 supports-[not(container-type:inline-size)]:lg:py-4"
			>
				{#if filterByAgent}
					<div class="flex items-center gap-2 mx-1">
						<Button
							variant="ghost"
							on:click={() => (selectingFilterAgent = true)}
							class="flex @2xl:hidden supports-[not(container-type:inline-size)]:lg:hidden relative p-0 aspect-square group"
						>
							<ArrowLeft size={20} class="text-[#344054]" />

							<Tooltip
								arrowSize={5}
								class="left-[calc(100%+8px)] top-1/2 -translate-y-1/2 z-20 opacity-0 group-hover:opacity-100 transition-opacity after:rotate-90 after:top-1/2 after:left-0 after:-translate-x-[100%] after:-translate-y-1/2"
							>
								Select agent
							</Tooltip>
						</Button>

						<a
							title={filterByAgent}
							href="/project/{$page.params.project_id}/chat-table/{filterByAgent}"
							class="relative flex items-center justify-between px-2 @2xl:px-3 supports-[not(container-type:inline-size)]:lg:px-4 py-[7px] @2xl:py-3 supports-[not(container-type:inline-size)]:lg:py-3 w-full bg-white data-dark:bg-[#303338] border border-[#E5E5E5] data-dark:border-[#484C55] rounded-md @2xl:rounded-lg supports-[not(container-type:inline-size)]:lg:rounded-xl {filterByAgent ===
							'_chat_'
								? 'pointer-events-none'
								: ''}"
						>
							<div class="flex items-center gap-2">
								<div
									class="flex-[0_0_auto] relative h-6 w-6 bg-[#F2F4F7] rounded-sm overflow-hidden"
								>
									<ChatAgentIcon
										class="absolute -bottom-[3px] left-1/2 -translate-x-1/2 h-[26px] aspect-square text-[#475467]"
									/>
								</div>
								<span
									class="font-medium text-sm @2xl:text-base supports-[not(container-type:inline-size)]:lg:text-base text-[#344054] line-clamp-1"
								>
									{filterByAgent === '_chat_' ? 'All agents' : filterByAgent}
								</span>
							</div>

							{#if filterByAgent && filterByAgent !== '_chat_'}
								<DropdownMenu.Root>
									<DropdownMenu.Trigger asChild let:builder>
										<Button
											builders={[builder]}
											variant="ghost"
											on:click={(e) => e.preventDefault()}
											title="Agent settings"
											class="absolute right-1.5 @2xl:right-3 supports-[not(container-type:inline-size)]:lg:right-4 flex-[0_0_auto] p-0 h-7 w-7 aspect-square"
										>
											<MoreVertIcon class="h-[18px] w-[18px]" />
										</Button>
									</DropdownMenu.Trigger>
									<DropdownMenu.Content alignOffset={-60} transitionConfig={{ x: 5, y: -5 }}>
										<DropdownMenu.Group>
											<DropdownMenu.Item
												on:click={() => (isEditingTableID = filterByAgent)}
												class="text-[#344054] data-[highlighted]:text-[#344054]"
											>
												<EditIcon class="h-3.5 w-3.5 mr-2" />
												<span>Rename agent</span>
											</DropdownMenu.Item>
											<ExportTableButton
												let:handleExportTable
												tableId={filterByAgent}
												tableType="chat"
											>
												<DropdownMenu.Item
													on:click={handleExportTable}
													class="text-[#344054] data-[highlighted]:text-[#344054]"
												>
													<ExportIcon class="h-3.5 w-3.5 mr-2" />
													<span>Export agent</span>
												</DropdownMenu.Item>
											</ExportTableButton>
											<DropdownMenu.Separator />
											<DropdownMenu.Item
												on:click={() => (isDeletingTable = filterByAgent)}
												class="text-destructive data-[highlighted]:text-destructive"
											>
												<Trash_2 class="h-3.5 w-3.5 mr-2" />
												<span>Delete agent</span>
											</DropdownMenu.Item>
										</DropdownMenu.Group>
									</DropdownMenu.Content>
								</DropdownMenu.Root>
							{/if}
						</a>
					</div>

					<div
						class="@container grid grid-cols-[minmax(0,auto)_min-content_min-content] h-min items-center px-1 sm:pt-1 overflow-auto sm:overflow-visible [scrollbar-gutter:stable]"
					>
						<div
							class="col-span-2 @2xl:col-span-1 supports-[not(container-type:inline-size)]:xl:col-span-1 flex-[0_0_auto] flex items-center gap-1"
						>
							<Button
								aria-label="Create table"
								on:click={() => (isAddingConversation = true)}
								class="flex-[0_0_auto] relative flex items-center justify-center gap-1.5 mb-[1px] px-2 xl:px-3 py-2 h-8 sm:h-9 text-xs xl:text-sm aspect-square xl:aspect-auto"
							>
								<AddIcon class="h-3.5 w-3.5" />
								<span class="hidden xl:block">Create table</span>
							</Button>

							<Button
								title="Import table"
								on:click={(e) => e.currentTarget.querySelector('input')?.click()}
								class="flex items-center gap-2 p-0 2xl:px-3.5 h-8 sm:h-9 text-[#475467] bg-[#F2F4F7] hover:bg-[#E4E7EC] focus-visible:bg-[#E4E7EC] active:bg-[#E4E7EC] aspect-square 2xl:aspect-auto"
							>
								<ImportIcon class="h-3.5" />

								<span class="hidden 2xl:block">Import table</span>

								<input
									id="chat-tbl-import"
									type="file"
									accept=".parquet"
									on:change|preventDefault={(e) =>
										handleFilesUpload(e, [...(e.currentTarget.files ?? [])])}
									multiple={false}
									class="fixed max-h-[0] max-w-0 !p-0 !border-none overflow-hidden"
								/>
							</Button>
						</div>

						<SearchBar
							bind:searchQuery
							{isLoadingSearch}
							debouncedSearch={debouncedSearchTables}
							label="Search table"
							placeholder="Search table"
							class="place-self-end lg:place-self-center {searchQuery
								? 'sm:w-[13.5rem]'
								: 'sm:has-[input:focus-visible]:w-[13.5rem]'}"
						/>

						<SorterSelect
							bind:sortOptions={$sortOptions}
							{sortableFields}
							{refetchTables}
							class="col-span-3 @2xl:col-span-1 supports-[not(container-type:inline-size)]:xl:col-span-1"
						/>
					</div>

					<div
						on:scroll={debounce((e) => scrollHandler(e, 'filtered'), 300)}
						style="grid-auto-rows: 120px;"
						class="grow grid grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] grid-flow-row gap-3 pt-1 px-1 h-1 overflow-auto [scrollbar-gutter:stable]"
					>
						{#if isLoadingFilteredConv}
							<div class="col-span-full flex items-center justify-center mx-auto p-4">
								<LoadingSpinner class="h-5 w-5 text-secondary" />
							</div>
						{:else}
							{#each filteredConversations as chatTable}
								<a
									href="/project/{$page.params.project_id}/chat-table/{chatTable.id}"
									title={chatTable.id}
									class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] rounded-lg hover:-translate-y-0.5 hover:shadow-float transition-[transform,box-shadow]"
								>
									<div
										class="grow flex items-start justify-between p-3 border-b border-[#E4E7EC] data-dark:border-[#333]"
									>
										<div class="flex items-start gap-1.5">
											<ChatTableIcon class="flex-[0_0_auto] h-5 w-5 text-[#475467]" />
											<span class="text-sm text-[#344054] break-all line-clamp-2">
												{chatTable.id}
											</span>
										</div>

										<DropdownMenu.Root>
											<DropdownMenu.Trigger asChild let:builder>
												<Button
													builders={[builder]}
													variant="ghost"
													on:click={(e) => e.preventDefault()}
													title="Table settings"
													class="flex-[0_0_auto] p-0 h-7 w-7 aspect-square translate-x-1.5 -translate-y-1.5"
												>
													<MoreVertIcon class="h-[18px] w-[18px]" />
												</Button>
											</DropdownMenu.Trigger>
											<DropdownMenu.Content alignOffset={-50} transitionConfig={{ x: 5, y: -5 }}>
												<DropdownMenu.Group>
													<DropdownMenu.Item
														on:click={() => (isEditingTableID = chatTable.id)}
														class="text-[#344054] data-[highlighted]:text-[#344054]"
													>
														<EditIcon class="h-3.5 w-3.5 mr-2" />
														<span>Rename table</span>
													</DropdownMenu.Item>
													<ExportTableButton
														let:handleExportTable
														tableId={chatTable.id}
														tableType="chat"
													>
														<DropdownMenu.Item
															on:click={handleExportTable}
															class="text-[#344054] data-[highlighted]:text-[#344054]"
														>
															<ExportIcon class="h-3.5 w-3.5 mr-2" />
															<span>Export table</span>
														</DropdownMenu.Item>
													</ExportTableButton>
													<DropdownMenu.Separator />
													<DropdownMenu.Item
														on:click={() => (isDeletingTable = chatTable.id)}
														class="text-destructive data-[highlighted]:text-destructive"
													>
														<Trash_2 class="h-3.5 w-3.5 mr-2" />
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
											class="font-medium text-xs text-[#98A2B3] data-dark:text-[#C9C9C9] line-clamp-1"
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
												class="w-min px-1 py-0.5 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
											>
												{chatTable.parent_id}
											</span>
										{/if}
									</div>
								</a>
							{/each}

							{#if isLoadingMoreFilteredConv}
								<div class="flex items-center justify-center mx-auto p-4">
									<LoadingSpinner class="h-5 w-5 text-secondary" />
								</div>
							{/if}
						{/if}
					</div>
				{:else}
					<span class="self-center my-auto font-medium text-[#999]">
						Select agent to filter conversations
					</span>
				{/if}
			</div>
		</div>
	{:else if loadingAgentsError.status === 404 && loadingAgentsError.org_id && userData?.member_of.find((org) => org.organization_id === loadingAgentsError?.org_id)}
		{@const projectOrg = userData?.member_of.find(
			(org) => org.organization_id === loadingAgentsError?.org_id
		)}
		<FoundProjectOrgSwitcher {projectOrg} />
	{:else}
		<div class="flex items-center justify-center mx-4 my-0 h-full">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{loadingAgentsError.status}
			</span>
			<div
				class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
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
