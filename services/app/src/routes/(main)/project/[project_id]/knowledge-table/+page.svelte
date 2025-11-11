<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { page } from '$app/state';
	import { kTableSort as sortOptions } from '$globalStore';
	import { pastKnowledgeTables } from '$lib/components/tables/tablesState.svelte';
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

	let { data } = $props();
	let { user } = $derived(data);

	let fetchController: AbortController | null = null;
	let loadingKTablesError: { status: number; message: string; org_id: string } | null =
		$state(null);
	let isLoadingKTables = $state(true);
	let isLoadingMoreKTables = $state(false); //TODO: Figure out infinite loop / pagination here
	let moreKTablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;
	const sortableFields = [
		{ id: 'id', title: 'Name', Icon: SortAlphabetIcon },
		{ id: 'updated_at', title: 'Date modified', Icon: SortByIcon }
	];

	let searchQuery = $state('');
	let searchController: AbortController | null = null;
	let isLoadingSearch = $state(false);

	let isAddingTable = $state(false);
	let isEditingTableID: string | null = $state(null);
	let isDeletingTable: string | null = $state(null);
	let isImportingTable: File | null = $state(null);

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
				order_ascending: $sortOptions.order === 'asc' ? 'true' : 'false',
				search_query: searchQuery.trim()
			} as Record<string, string>;

			if (searchParams.search_query === '') {
				delete searchParams.search_query;
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/list?` +
					new URLSearchParams(searchParams),
				{
					credentials: 'same-origin',
					signal: fetchController.signal
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
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/knowledge/list?${new URLSearchParams({
					limit: limit.toString(),
					order_by: $sortOptions.orderBy,
					order_ascending: $sortOptions.order === 'asc' ? 'true' : 'false',
					search_query: q
				})}`,
				{
					signal: searchController.signal
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

{#if !loadingKTablesError}
	<div class="flex h-full flex-col pb-3">
		<div
			class="grid h-min min-w-0 grid-cols-[12rem_min-content_minmax(0,auto)_min-content_min-content] items-center gap-1 overflow-auto px-7 pb-0.5 pt-1 [scrollbar-gutter:stable] sm:overflow-visible sm:pb-2 sm:pt-3"
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
				onclick={() => (isAddingTable = true)}
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
					id="knowledge-tbl-import"
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
			onscroll={debounce(scrollHandler, 400)}
			style="grid-auto-rows: 112px;"
			class="grid h-1 grow grid-flow-row grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3 overflow-auto px-7 pt-1 [scrollbar-gutter:stable]"
		>
			{#if isLoadingKTables}
				{#each Array(12) as _}
					<Skeleton
						class="flex flex-col items-center justify-center gap-2 rounded-lg bg-black/[0.09] data-dark:bg-white/[0.1]"
					/>
				{/each}
			{:else}
				{#each $pastKnowledgeTables as knowledgeTable (knowledgeTable.id)}
					<a
						href="/project/{page.params.project_id}/knowledge-table/{encodeURIComponent(
							knowledgeTable.id
						)}"
						title={knowledgeTable.id}
						class="flex flex-col rounded-lg border border-[#E4E7EC] bg-white transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-float data-dark:border-[#333] data-dark:bg-[#42464E]"
					>
						<div class="flex w-full grow items-start justify-between p-3">
							<div class="flex items-start gap-1">
								<KnowledgeTableIcon class="h-5 w-5 flex-[0_0_auto] text-[#475467]" />
								<span class="line-clamp-2 break-all text-sm text-[#344054]">
									{knowledgeTable.id}
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
											onclick={() => (isEditingTableID = knowledgeTable.id)}
											class="text-[#344054] data-[highlighted]:text-[#344054]"
										>
											<EditIcon class="mr-2 h-3.5 w-3.5" />
											<span>Rename table</span>
										</DropdownMenu.Item>
										<ExportTableButton tableId={knowledgeTable.id} tableType="knowledge">
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
											onclick={() => (isDeletingTable = knowledgeTable.id)}
											class="text-destructive data-[highlighted]:text-destructive"
										>
											<Trash_2 class="mr-2 h-3.5 w-3.5" />
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
								class="line-clamp-1 text-xs font-medium text-[#98A2B3] data-dark:text-[#C9C9C9]"
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
					<div class="mx-auto flex items-center justify-center p-4">
						<LoadingSpinner class="h-5 w-5 text-secondary" />
					</div>
				{/if}
			{/if}
		</div>
	</div>
{:else if loadingKTablesError.status === 404 && loadingKTablesError.org_id && user?.org_memberships.find((org) => org.organization_id === loadingKTablesError?.org_id)}
	{@const projectOrg = user?.organizations.find((org) => org.id === loadingKTablesError?.org_id)}
	<FoundProjectOrgSwitcher {projectOrg} />
{:else}
	<div class="mx-4 my-0 flex h-full items-center justify-center">
		<span class="relative -top-[0.05rem] text-3xl font-extralight">
			{loadingKTablesError.status}
		</span>
		<div
			class="ml-4 flex min-h-10 items-center border-l border-[#ccc] pl-4 data-dark:border-[#666]"
		>
			<h1>{loadingKTablesError.message}</h1>
		</div>
	</div>
{/if}

<AddTableDialog bind:isAddingTable />
<RenameTableDialog tableType="knowledge" bind:isEditingTableID />
<DeleteTableDialog tableType="knowledge" bind:isDeletingTable />
<ImportTableDialog tableType="knowledge" bind:isImportingTable {refetchTables} />
