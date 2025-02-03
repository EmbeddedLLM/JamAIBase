<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import debounce from 'lodash/debounce';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import {
		activeProject,
		activeOrganization,
		projectSort as sortOptions,
		uploadQueue
	} from '$globalStore';
	import logger from '$lib/logger';
	import type { Project } from '$lib/types';

	import ProjectDialogs from './ProjectDialogs.svelte';
	import ExportProjectButton from './ExportProjectButton.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import SorterSelect from '$lib/components/preset/SorterSelect.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import SortAlphabetIcon from '$lib/icons/SortAlphabetIcon.svelte';
	import SortByIcon from '$lib/icons/SortByIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	export let data;
	$: ({ activeOrganizationId } = data);

	let fetchController: AbortController | null = null;
	let orgProjects: Project[] = [];
	let loadingProjectsError: { status: number; message: string } | null = null;
	let isLoadingProjects = true;
	let isLoadingMoreProjects = false;
	let moreProjectsFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;
	const sortableFields = [
		{ id: 'name', title: 'Name', Icon: SortAlphabetIcon },
		{ id: 'created_at', title: 'Date created', Icon: SortByIcon },
		{ id: 'updated_at', title: 'Date modified', Icon: SortByIcon }
	];

	let searchQuery = '';
	let searchController: AbortController | null = null;
	let isLoadingSearch = false;

	let isAddingProject = false;
	let isEditingProjectName: Project | null = null;
	let isDeletingProject: string | null = null;

	$: if (browser && activeOrganizationId) refetchProjects();

	onMount(() => {
		return () => {
			fetchController?.abort('Navigated');
			orgProjects = [];
		};
	});

	async function getProjects() {
		if (!isLoadingProjects) {
			isLoadingMoreProjects = true;
		}

		fetchController = new AbortController();

		try {
			const searchParams = new URLSearchParams({
				offset: currentOffset.toString(),
				limit: limit.toString(),
				order_by: $sortOptions.orderBy,
				order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
				search_query: searchQuery.trim()
			});

			if (searchParams.get('search_query') === '') {
				searchParams.delete('search_query');
			}

			if (PUBLIC_IS_LOCAL !== 'false') {
				searchParams.append('organization_id', 'default');
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects?${searchParams}`,
				{
					credentials: 'same-origin',
					signal: fetchController.signal
				}
			);
			currentOffset += limit;

			if (response.status == 200) {
				const moreProjects = await response.json();
				if (moreProjects.items.length) {
					orgProjects = [...orgProjects, ...moreProjects.items];
				} else {
					//* Finished loading oldest conversation
					moreProjectsFinished = true;
				}
			} else {
				const responseBody = await response.json();
				console.error(responseBody);
				toast.error('Failed to fetch projects', {
					id: responseBody.err_message?.message || JSON.stringify(responseBody),
					description: CustomToastDesc,
					componentProps: {
						description: responseBody.err_message?.message || JSON.stringify(responseBody),
						requestID: responseBody.err_message?.request_id
					}
				});
				loadingProjectsError = {
					status: response.status,
					message: responseBody.err_message
				};
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated') {
				console.error(err);
			}
		}

		isLoadingProjects = false;
		isLoadingMoreProjects = false;
	}

	async function refetchProjects() {
		if (searchQuery) {
			await handleSearchProjects(searchQuery);
		} else {
			searchController?.abort('Duplicate');
			orgProjects = [];
			currentOffset = 0;
			moreProjectsFinished = false;
			await getProjects();
			isLoadingSearch = false;
		}
	}

	async function handleImportProject(
		e: Event & {
			currentTarget: EventTarget & HTMLInputElement;
		},
		files: File[]
	) {
		e.currentTarget.value = '';

		if (!$activeOrganization) return;
		if (files.length === 0) return;
		if (files.length > 1) {
			alert('Cannot import multiple projects at the same time');
			return;
		}

		const allowedFiletypes = ['.parquet'];
		if (
			files.some((file) => !allowedFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase()))
		) {
			alert(`Files must be of type: ${allowedFiletypes.join(', ').replaceAll('.', '')}`);
			return;
		}

		const formData = new FormData();
		formData.append('file', files[0]);
		// formData.append('project_id_dst', '');

		$uploadQueue = {
			...$uploadQueue,
			queue: [
				...$uploadQueue.queue,
				{
					file: files[0],
					request: {
						method: 'POST',
						url: `${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/import/${$activeOrganization.organization_id}`,
						data: formData,
						headers: {
							'Content-Type': 'multipart/form-data'
						}
					},
					completeText: 'Importing project...',
					successText: `Imported to: ${$activeOrganization.organization_name}`,
					invalidate: refetchProjects
				}
			]
		};
	}

	async function handleSearchProjects(q: string) {
		isLoadingSearch = true;

		if (!searchQuery) return refetchProjects();

		searchController?.abort('Duplicate');
		searchController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects?${new URLSearchParams({
					limit: limit.toString(),
					order_by: $sortOptions.orderBy,
					order_descending: $sortOptions.order === 'asc' ? 'false' : 'true',
					search_query: q
				})}`,
				{
					signal: searchController.signal
				}
			);
			currentOffset = limit;
			moreProjectsFinished = false;

			const responseBody = await response.json();
			if (response.ok) {
				orgProjects = responseBody.items;
			} else {
				logger.error('PROJECT_LIST_SEARCH', responseBody);
				console.error(responseBody);
				toast.error('Failed to search projects', {
					id: responseBody.err_message?.message || JSON.stringify(responseBody),
					description: CustomToastDesc,
					componentProps: {
						description: responseBody.err_message?.message || JSON.stringify(responseBody),
						requestID: responseBody.err_message?.request_id
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
	const debouncedSearchProjects = debounce(handleSearchProjects, 300);

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (offset < LOAD_THRESHOLD && !isLoadingProjects && !moreProjectsFinished) {
			await getProjects();
		}
	};
</script>

<svelte:head>
	<title>Projects</title>
</svelte:head>

<section class="grow relative flex flex-col gap-2 h-1 overflow-auto">
	<div class="relative flex flex-col gap-2 md:pt-3 pb-0 pl-7 pr-6">
		<div class="flex items-center gap-3 pl-1 pt-0.5 text-[#344054]">
			<AssignmentIcon class="h-5" />
			<h1 class="text-xl">Projects</h1>
		</div>

		<div class="static xs:absolute right-7">
			<InputText
				on:input={({ detail: e }) => {
					//@ts-expect-error Generic type
					debouncedSearchProjects(e.target?.value ?? '');
				}}
				bind:value={searchQuery}
				type="search"
				placeholder="Search Project"
				class="pl-8 h-9 w-[16rem] placeholder:not-italic placeholder:text-[#98A2B3] bg-[#F2F4F7] rounded-full"
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
	</div>

	<div on:scroll={debounce(scrollHandler, 300)} class="overflow-auto [scrollbar-gutter:stable]">
		<div class="flex gap-3 pt-2 pb-0 px-7 min-h-0">
			<button
				on:click={() => (isAddingProject = true)}
				class="flex flex-col items-center justify-center gap-2 min-h-36 w-40 bg-[#FFEBEF] hover:bg-[#F5E2E5] rounded-lg transition-colors duration-300 group"
			>
				<div
					class="flex items-center justify-center h-11 bg-[#BF416E] rounded-full aspect-square group-hover:scale-105 transition-transform duration-300"
				>
					<AddIcon class="h-5 w-5 text-white" />
				</div>

				<span class=" text-sm text-[#475467]"> New Project </span>
			</button>

			<button
				on:click={(e) => e.currentTarget.querySelector('input')?.click()}
				class="flex flex-col items-center justify-center gap-2 min-h-36 w-40 bg-[#EBEFFB] hover:bg-[#E2E5F1] rounded-lg transition-colors duration-300 group"
			>
				<div
					class="flex items-center justify-center h-11 bg-[#4169E1] rounded-full aspect-square group-hover:scale-105 transition-transform duration-300"
				>
					<ImportIcon class="h-5 w-5 text-white" />
				</div>

				<span class=" text-sm text-[#475467]"> Import Project </span>

				<input
					id="project-import"
					type="file"
					accept=".parquet"
					on:change|preventDefault={(e) =>
						handleImportProject(e, [...(e.currentTarget.files ?? [])])}
					multiple={false}
					class="fixed max-h-[0] max-w-0 !p-0 !border-none overflow-hidden"
				/>
			</button>
		</div>

		<div class="flex flex-col gap-1.5 pt-6 pb-0 px-6 min-h-0">
			<div class="relative flex flex-col">
				<h2 class="pl-1 text-xl">All Projects</h2>

				<SorterSelect
					bind:sortOptions={$sortOptions}
					{sortableFields}
					refetchTables={refetchProjects}
					class="static xs:absolute right-1"
				/>
			</div>

			{#if !loadingProjectsError}
				<div
					style="grid-auto-rows: 128px;"
					class="grow grid grid-cols-[minmax(15rem,1fr)] sm:grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] grid-flow-row gap-4 pt-1 pb-4 px-1"
				>
					{#if isLoadingProjects}
						{#each Array(8) as _}
							<Skeleton
								class="flex flex-col items-center justify-center gap-2 bg-black/[0.09] data-dark:bg-white/[0.1] rounded-lg"
							/>
						{/each}
					{:else}
						{#each orgProjects ?? [] as project (project.id)}
							<a
								on:click={() => ($activeProject = project)}
								href="/project/{project.id}"
								title={project.id}
								class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E5E5E5] data-dark:border-[#333] rounded-lg hover:-translate-y-0.5 hover:shadow-float transition-[transform,box-shadow]"
							>
								<div
									class="grow flex items-start justify-between p-3 border-b border-[#E5E5E5] data-dark:border-[#333]"
								>
									<div class="flex items-start gap-1.5">
										<span class="bg-[#FFEFF2] rounded p-1">
											<AssignmentIcon class="flex-[0_0_auto] h-4 w-4 text-[#950048]" />
										</span>
										<span class="text-[#344054] [word-break:break-word] line-clamp-2">
											{project.name}
										</span>
									</div>

									<DropdownMenu.Root>
										<DropdownMenu.Trigger asChild let:builder>
											<Button
												variant="ghost"
												on:click={(e) => e.preventDefault()}
												builders={[builder]}
												title="Project settings"
												class="flex-[0_0_auto] p-0 h-7 w-7 aspect-square translate-x-1.5 -translate-y-1.5"
											>
												<MoreVertIcon class="h-[18px] w-[18px]" />
											</Button>
										</DropdownMenu.Trigger>
										<DropdownMenu.Content
											data-testid="project-settings-dropdown"
											alignOffset={-60}
											transitionConfig={{ x: 5, y: -5 }}
										>
											<DropdownMenu.Group>
												<DropdownMenu.Item
													on:click={() => (isEditingProjectName = project)}
													class="text-[#344054] data-[highlighted]:text-[#344054]"
												>
													<EditIcon class="h-3.5 w-3.5 mr-2" />
													<span>Rename project</span>
												</DropdownMenu.Item>
												<ExportProjectButton let:handleExportProject>
													<DropdownMenu.Item
														on:click={() => handleExportProject(project.id)}
														class="text-[#344054] data-[highlighted]:text-[#344054]"
													>
														<ExportIcon class="h-3.5 mr-2" />
														<span>Export project</span>
													</DropdownMenu.Item>
												</ExportProjectButton>
												<DropdownMenu.Separator />
												<DropdownMenu.Item
													on:click={() => (isDeletingProject = project.id)}
													class="text-destructive data-[highlighted]:text-destructive"
												>
													<Trash_2 class="h-3.5 w-3.5 mr-2" />
													<span>Delete project</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								</div>

								<div class="flex px-3 py-2">
									<span
										title={new Date(project.updated_at).toLocaleString(undefined, {
											month: 'long',
											day: 'numeric',
											year: 'numeric'
										})}
										class="font-medium text-xs text-[#98A2B3] data-dark:text-[#C9C9C9] line-clamp-1"
									>
										Last updated
										<span class="text-[#475467]">
											{new Date(project.updated_at).toLocaleString(undefined, {
												month: 'long',
												day: 'numeric',
												year: 'numeric'
											})}
										</span>
									</span>
								</div>
							</a>
						{/each}
					{/if}

					{#if isLoadingMoreProjects}
						<div class="flex items-center justify-center mx-auto p-4">
							<LoadingSpinner class="h-5 w-5 text-secondary" />
						</div>
					{/if}
				</div>
			{:else}
				<div class="flex items-center justify-center mx-48 my-0 h-64">
					<span class="relative -top-[0.05rem] text-3xl font-extralight">
						{loadingProjectsError.status}
					</span>
					<div
						class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
					>
						<h1>{JSON.stringify(loadingProjectsError.message)}</h1>
					</div>
				</div>
			{/if}
		</div>
	</div>
</section>

<ProjectDialogs
	bind:isAddingProject
	bind:isEditingProjectName
	bind:isDeletingProject
	{orgProjects}
	{refetchProjects}
/>
