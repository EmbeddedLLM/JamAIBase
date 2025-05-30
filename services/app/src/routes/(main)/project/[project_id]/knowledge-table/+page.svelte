<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { page } from '$app/stores';
	import { kTableSort as sortOptions } from '$globalStore';
	import { pastKnowledgeTables } from '$lib/components/tables/tablesStore';
	import logger from '$lib/logger';

	import { AddTableDialog } from './(dialogs)';
	import { ExportTableButton } from '../(components)';
	import { DeleteTableDialog, ImportTableDialog, RenameTableDialog } from '../(dialogs)';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import SorterSelect from '$lib/components/preset/SorterSelect.svelte';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import KnowledgeTableIcon from '$lib/icons/KnowledgeTableIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import SortAlphabetIcon from '$lib/icons/SortAlphabetIcon.svelte';
	import SortByIcon from '$lib/icons/SortByIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	export let data;
	$: ({ userData } = data);

	let windowWidth: number;

	let fetchController: AbortController | null = null;
	let loadingKTablesError: { status: number; message: string; org_id: string } | null = null;
	let isLoadingKTables = true;
	let isLoadingMoreKTables = false; //TODO: Figure out infinite loop / pagination here
	let moreKTablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;
	const sortableFields = [
		{ id: 'id', title: 'Name', Icon: SortAlphabetIcon },
		{ id: 'updated_at', title: 'Date modified', Icon: SortByIcon }
	];

	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let isAddingTable = false;
	let isEditingTableID: string | null = null;
	let isDeletingTable: string | null = null;
	let isImportingTable: File | null = null;

	onMount(() => {
		getKnowledgeTables();

		return () => {
			fetchController?.abort('Navigated');
			$pastKnowledgeTables = [];
		};
	});

	async function getKnowledgeTables() {
		if (!isLoadingKTables) {
			isLoadingMoreKTables = true;
		}

		fetchController = new AbortController();

		try {
			const searchParams = {
				offset: currentOffset.toString(),
				limit: limit.toString(),
				order_by: $sortOptions.orderBy,
				order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
				search_query: searchQuery.trim()
			} as Record<string, string>;

			if (searchParams.search_query === '') {
				delete searchParams.search_query;
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?` + new URLSearchParams(searchParams),
				{
					credentials: 'same-origin',
					signal: fetchController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
				}
			);
			currentOffset += limit;

			if (response.status == 200) {
				const moreKnowledgeTables = await response.json();
				if (moreKnowledgeTables.items.length) {
					$pastKnowledgeTables = [...$pastKnowledgeTables, ...moreKnowledgeTables.items];
				} else {
					//* Finished loading oldest conversation
					moreKTablesFinished = true;
				}
			} else {
				const responseBody = await response.json();
				if (response.status !== 404) {
					logger.error('KNOWTBL_LIST_TBL', responseBody);
				}
				console.error(responseBody);
				toast.error('Failed to fetch knowledge tables', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
				loadingKTablesError = {
					status: response.status,
					message: responseBody.message,
					org_id: responseBody.org_id
				};
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated') {
				console.error(err);
			}
		}

		isLoadingKTables = false;
		isLoadingMoreKTables = false;
	}

	async function refetchTables() {
		if (searchQuery) {
			await handleSearchTables(searchQuery);
		} else {
			searchController?.abort('Duplicate');
			$pastKnowledgeTables = [];
			currentOffset = 0;
			moreKTablesFinished = false;
			await getKnowledgeTables();
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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?${new URLSearchParams({
					limit: limit.toString(),
					order_by: $sortOptions.orderBy,
					order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
					search_query: q
				})}`,
				{
					signal: searchController.signal,
					headers: {
						'x-project-id': $page.params.project_id
					}
				}
			);
			currentOffset = limit;
			moreKTablesFinished = false;

			const responseBody = await response.json();
			if (response.ok) {
				$pastKnowledgeTables = responseBody.items;
			} else {
				logger.error('KNOWTBL_TBL_SEARCHTBL', responseBody);
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

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (offset < LOAD_THRESHOLD && !isLoadingMoreKTables && !moreKTablesFinished) {
			await getKnowledgeTables();
		}
	};
</script>

<svelte:head>
	<title>Knowledge Table</title>
</svelte:head>

<svelte:window bind:innerWidth={windowWidth} />

{#if !loadingKTablesError}
	<div class="flex flex-col pb-3 h-full">
		<div
			class="grid grid-cols-[minmax(0,auto)_min-content_min-content] h-min items-center gap-1 px-7 py-1.5 sm:py-4 overflow-auto sm:overflow-visible [scrollbar-gutter:stable]"
		>
			<div class="col-span-2 lg:col-span-1 flex-[0_0_auto] flex items-center gap-1">
				<Button
					aria-label="Create table"
					on:click={() => (isAddingTable = true)}
					class="flex-[0_0_auto] relative flex items-center justify-center gap-1.5 px-2 xs:px-3 py-2 h-8 xs:h-9 text-xs sm:text-sm aspect-square xs:aspect-auto"
				>
					<AddIcon class="h-3.5 w-3.5" />
					<span class="hidden xs:block">Create table</span>
				</Button>

				<Button
					title="Import table"
					on:click={(e) => e.currentTarget.querySelector('input')?.click()}
					class="flex items-center gap-2 p-0 md:px-3.5 h-8 xs:h-9 text-[#475467] bg-[#F2F4F7] hover:bg-[#E4E7EC] focus-visible:bg-[#E4E7EC] active:bg-[#E4E7EC]  aspect-square md:aspect-auto"
				>
					<ImportIcon class="h-3.5" />

					<span class="hidden md:block">Import table</span>

					<input
						id="knowledge-tbl-import"
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
				class=""
			/>

			<SorterSelect
				bind:sortOptions={$sortOptions}
				{sortableFields}
				{refetchTables}
				class="col-span-3 lg:col-span-1"
			/>
		</div>

		<div
			on:scroll={debounce(scrollHandler, 400)}
			style="grid-auto-rows: 112px;"
			class="grow grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] grid-flow-row gap-3 pt-1 px-7 h-1 overflow-auto [scrollbar-gutter:stable]"
		>
			{#if isLoadingKTables}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
					/>
				{/each}
			{:else}
				{#each $pastKnowledgeTables as knowledgeTable (knowledgeTable.id)}
					<a
						href="/project/{$page.params.project_id}/knowledge-table/{knowledgeTable.id}"
						title={knowledgeTable.id}
						class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] rounded-lg hover:-translate-y-0.5 hover:shadow-float transition-[transform,box-shadow]"
					>
						<div
							class="grow flex items-start justify-between p-3 w-full border-b border-[#E4E7EC] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1">
								<KnowledgeTableIcon class="flex-[0_0_auto] h-5 w-5 text-[#475467]" />
								<span class="text-sm text-[#344054] break-all line-clamp-2">
									{knowledgeTable.id}
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
											on:click={() => (isEditingTableID = knowledgeTable.id)}
											class="text-[#344054] data-[highlighted]:text-[#344054]"
										>
											<EditIcon class="h-3.5 w-3.5 mr-2" />
											<span>Rename table</span>
										</DropdownMenu.Item>
										<ExportTableButton
											let:handleExportTable
											tableId={knowledgeTable.id}
											tableType="knowledge"
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
											on:click={() => (isDeletingTable = knowledgeTable.id)}
											class="text-destructive data-[highlighted]:text-destructive"
										>
											<Trash_2 class="h-3.5 w-3.5 mr-2" />
											<span>Delete table</span>
										</DropdownMenu.Item>
									</DropdownMenu.Group>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</div>

						<div class="flex px-3 py-2">
							<span
								title={new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
								class="font-medium text-xs text-[#98A2B3] data-dark:text-[#C9C9C9] line-clamp-1"
							>
								Last updated
								<span class="text-[#475467]">
									{new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
										month: 'long',
										day: 'numeric',
										year: 'numeric'
									})}
								</span>
							</span>
						</div>
					</a>
				{/each}

				{#if isLoadingMoreKTables}
					<div class="flex items-center justify-center mx-auto p-4">
						<LoadingSpinner class="h-5 w-5 text-secondary" />
					</div>
				{/if}
			{/if}
		</div>
	</div>
{:else if loadingKTablesError.status === 404 && loadingKTablesError.org_id && userData?.member_of.find((org) => org.organization_id === loadingKTablesError?.org_id)}
	{@const projectOrg = userData?.member_of.find(
		(org) => org.organization_id === loadingKTablesError?.org_id
	)}
	<FoundProjectOrgSwitcher {projectOrg} />
{:else}
	<div class="flex items-center justify-center mx-4 my-0 h-full">
		<span class="relative -top-[0.05rem] text-3xl font-extralight">
			{loadingKTablesError.status}
		</span>
		<div
			class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
		>
			<h1>{loadingKTablesError.message}</h1>
		</div>
	</div>
{/if}

<AddTableDialog bind:isAddingTable />
<RenameTableDialog tableType="knowledge" bind:isEditingTableID />
<DeleteTableDialog tableType="knowledge" bind:isDeletingTable />
<ImportTableDialog tableType="knowledge" bind:isImportingTable {refetchTables} />
