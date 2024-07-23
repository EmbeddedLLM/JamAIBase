<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { page } from '$app/stores';
	import { pastKnowledgeTables } from '../tablesStore';
	import logger from '$lib/logger';

	import { AddTableDialog } from './(dialogs)';
	import { DeleteTableDialog, RenameTableDialog } from '../(dialogs)';
	import { toast } from 'svelte-sonner';
	import FoundProjectOrgSwitcher from '$lib/components/preset/FoundProjectOrgSwitcher.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import RowIcon from '$lib/icons/RowIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';

	export let data;
	$: ({ userData } = data);

	let fetchController: AbortController | null = null;
	let loadingKTablesError: { status: number; message: string; org_id: string } | null = null;
	let isLoadingKTables = true;
	let isLoadingMoreKTables = false; //TODO: Figure out infinite loop / pagination here
	let moreKTablesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	let isAddingTable = false;
	let isEditingTableID: string | null = null;
	let isDeletingTable: string | null = null;

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
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge?` +
					new URLSearchParams({
						offset: currentOffset.toString(),
						limit: limit.toString()
					}),
				{
					method: 'GET',
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
					description: responseBody.message || JSON.stringify(responseBody)
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

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 20; //? Minimum offset scroll height to load more conversations

		if (offset < LOAD_THRESHOLD && !isLoadingMoreKTables && !moreKTablesFinished) {
			await getKnowledgeTables();
		}
	};
</script>

<svelte:head>
	<title>Knowledge Table</title>
</svelte:head>

{#if !loadingKTablesError}
	<div class="flex flex-col gap-6 px-7 py-3 h-full">
		<div class="flex justify-between px-1">
			<div class="grid grid-cols-3">
				<Button
					variant="action"
					on:click={() => (isAddingTable = true)}
					class="flex items-center justify-center gap-2 px-6"
				>
					<AddIcon class="mb-0.5 h-3 text-black aspect-square" />

					<span class="font-medium text-sm">New Table</span>
				</Button>
			</div>

			<!-- <div>Search</div> -->
		</div>

		<div
			on:scroll={debounce(scrollHandler, 400)}
			style="grid-auto-rows: 112px;"
			class="grow grid grid-cols-2 lg:grid-cols-4 2xl:grid-cols-6 grid-flow-row gap-4 pt-1 px-1 h-1 overflow-auto"
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
						href={`/project/${$page.params.project_id}/knowledge-table/${knowledgeTable.id}`}
						title={knowledgeTable.id}
						class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E4E7EC] data-dark:border-[#333] rounded-lg hover:-translate-y-0.5 hover:shadow-float transition-[transform,box-shadow]"
					>
						<div
							class="grow flex items-start justify-between p-3 w-full border-b border-[#E4E7EC] data-dark:border-[#333]"
						>
							<div class="flex items-start gap-1.5">
								<RowIcon class="flex-[0_0_auto] h-5 w-5 text-secondary" />
								<span class="font-medium text-sm break-all line-clamp-2">{knowledgeTable.id}</span>
							</div>

							<DropdownMenu.Root>
								<DropdownMenu.Trigger asChild let:builder>
									<Button
										on:click={(e) => e.preventDefault()}
										builders={[builder]}
										variant="ghost"
										title="Table settings"
										class="p-0 h-7 w-7 aspect-square rounded-full translate-x-1.5 -translate-y-1"
									>
										<MoreVertIcon class="h-[18px] w-[18px]" />
									</Button>
								</DropdownMenu.Trigger>
								<DropdownMenu.Content alignOffset={-50} transitionConfig={{ x: 5, y: -5 }}>
									<!-- <DropdownMenu.Group>
											<DropdownMenu.Item on:click={() => {}}>
												<CheckIcon class="h-4 w-4 mr-2 mb-[1px]" />
												<span>Select</span>
											</DropdownMenu.Item>
										</DropdownMenu.Group>
										<DropdownMenu.Separator /> -->
									<DropdownMenu.Group>
										<DropdownMenu.Item on:click={() => (isEditingTableID = knowledgeTable.id)}>
											<EditIcon class="h-4 w-4 mr-2 mb-[2px]" />
											<span>Rename table</span>
										</DropdownMenu.Item>
										<DropdownMenu.Item on:click={() => (isDeletingTable = knowledgeTable.id)}>
											<Trash_2 class="h-4 w-4 mr-2 mb-[2px]" />
											<span>Delete table</span>
										</DropdownMenu.Item>
									</DropdownMenu.Group>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</div>

						<div class="flex p-3">
							<span
								title={new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
								class="text-xs text-[#999] data-dark:text-[#C9C9C9] line-clamp-1"
							>
								Updated at: {new Date(knowledgeTable.updated_at).toLocaleString(undefined, {
									month: 'long',
									day: 'numeric',
									year: 'numeric'
								})}
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
{:else if loadingKTablesError.status === 404 && loadingKTablesError.org_id && userData?.organizations.find((org) => org.organization_id === loadingKTablesError?.org_id)}
	{@const projectOrg = userData?.organizations.find(
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
