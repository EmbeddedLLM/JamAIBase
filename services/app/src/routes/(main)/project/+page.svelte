<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import debounce from 'lodash/debounce';
	import { Clipboard, ClipboardPlus, Compass, Trash2 } from '@lucide/svelte';
	import {
		activeProject,
		activeOrganization,
		projectSort as sortOptions,
		uploadQueue
	} from '$globalStore';
	import { tagColors } from '$lib/constants';
	import logger from '$lib/logger';
	import type { Project } from '$lib/types';

	import ExportProjectButton from './ExportProjectButton.svelte';
	import ProjectDialogs from './ProjectDialogs.svelte';
	import ProjectsThumbsFetch from './ProjectsThumbsFetch.svelte';
	import { m } from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import InputText from '$lib/components/InputText.svelte';
	import SorterSelect from '$lib/components/preset/SorterSelect.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import SortAlphabetIcon from '$lib/icons/SortAlphabetIcon.svelte';
	import SortByIcon from '$lib/icons/SortByIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	let { data } = $props();
	let { activeOrganizationId } = $derived(data);

	let fetchController: AbortController | null = null;
	let orgProjects: Project[] = $state([]);
	let loadingProjectsError: { status: number; message: string } | null = $state(null);
	let isLoadingProjects = $state(true);
	let isLoadingMoreProjects = $state(false);
	let moreProjectsFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;
	const sortableFields = [
		{ id: 'name', title: m['sortable.name'](), Icon: SortAlphabetIcon },
		{ id: 'created_at', title: m['sortable.created_at'](), Icon: SortByIcon },
		{ id: 'updated_at', title: m['sortable.updated_at'](), Icon: SortByIcon }
	];

	let projectsThumbs = $state<{ [projectID: string]: string }>({});

	let searchQuery = $state('');
	let isLoadingSearch = $state(false);

	let isAddingProject = $state(page.url.searchParams.has('new'));
	let isEditingProjectName: Project | null = $state(null);
	let isDeletingProject: string | null = $state(null);

	$effect(() => {
		if (browser && activeOrganizationId) refetchProjects();
	});

	onMount(() => {
		return () => {
			fetchController?.abort('Navigated');
			orgProjects = [];
		};
	});

	async function getProjects() {
		if (!$activeOrganization) return;
		if (!isLoadingProjects) {
			isLoadingMoreProjects = true;
		}

		fetchController = new AbortController();

		try {
			const searchParams = new URLSearchParams([
				['offset', currentOffset.toString()],
				['limit', limit.toString()],
				['order_by', $sortOptions.orderBy],
				['order_ascending', $sortOptions.order === 'asc' ? 'true' : 'false'],
				['organization_id', $activeOrganization.id]
			]);

			if (searchQuery.trim() !== '') {
				searchParams.append('search_query', searchQuery.trim());
			}

			const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/projects/list?${searchParams}`, {
				credentials: 'same-origin',
				signal: fetchController.signal
			});
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
					id: responseBody?.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody?.message || JSON.stringify(responseBody),
						requestID: responseBody?.request_id
					}
				});
				loadingProjectsError = {
					status: response.status,
					message: responseBody
				};
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated' && err !== 'Duplicate') {
				console.error(err);
			}
		}

		isLoadingProjects = false;
		isLoadingMoreProjects = false;
	}

	async function refetchProjects() {
		fetchController?.abort('Duplicate');
		orgProjects = [];
		currentOffset = 0;
		moreProjectsFinished = false;
		await tick();
		await getProjects();
		isLoadingSearch = false;
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
			files.some(
				(file) => !allowedFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(`Files must be of type: ${allowedFiletypes.join(', ').replaceAll('.', '')}`);
			return;
		}

		const formData = new FormData();
		formData.append('file', files[0]);
		// formData.append('project_id', '');
		formData.append('organization_id', $activeOrganization.id);

		$uploadQueue = {
			...$uploadQueue,
			queue: [
				...$uploadQueue.queue,
				{
					file: files[0],
					request: {
						method: 'POST',
						url: `${PUBLIC_JAMAI_URL}/api/owl/projects/import/parquet`,
						data: formData,
						headers: {
							'Content-Type': 'multipart/form-data'
						}
					},
					completeText: 'Importing project...',
					successText: `Imported to: ${$activeOrganization.name}`,
					invalidate: refetchProjects
				}
			]
		};
	}

	const debouncedSearchProjects = debounce((e) => {
		searchQuery = e.target?.value;
		isLoadingSearch = true;
		refetchProjects();
	}, 300);

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (
			orgProjects.length > 0 &&
			offset < LOAD_THRESHOLD &&
			!isLoadingProjects &&
			!moreProjectsFinished
		) {
			fetchController?.abort('Duplicate');
			await getProjects();
		}
	};
</script>

<svelte:head>
	<title>{m['project.heading']()}</title>
</svelte:head>

<section
	onscroll={debounce(scrollHandler, 300)}
	class="relative flex h-1 grow flex-col gap-2 overflow-auto [scrollbar-gutter:stable]"
>
	<div class="flex flex-col gap-2 pb-0 pl-7 pr-6 md:pt-3">
		<div class="flex items-center gap-3 pl-1 pt-0.5 text-[#344054]">
			<h1 class="text-xl">{m['project.heading']()}</h1>
		</div>
	</div>

	<div>
		<div class="flex min-h-0 gap-3 overflow-auto px-7 pb-0 pt-2">
			<button
				onclick={() => (isAddingProject = true)}
				class="group flex min-h-36 min-w-40 flex-col items-center justify-center gap-2 rounded-lg bg-[#FFEBEF] transition-colors duration-300 hover:bg-[#F5E2E5]"
			>
				<div
					class="flex aspect-square h-11 items-center justify-center rounded-full bg-[#BF416E] transition-transform duration-300 group-hover:scale-105"
				>
					<AddIcon class="h-5 w-5 text-white" />
				</div>

				<span class=" text-sm text-[#475467]">{m['project.create_btn']()}</span>
			</button>

			<a
				href="/join-project"
				class="group flex min-h-36 min-w-40 flex-col items-center justify-center gap-2 rounded-lg bg-[#FFEBEF] transition-colors duration-300 hover:bg-[#F5E2E5]"
			>
				<div
					class="flex aspect-square h-11 items-center justify-center rounded-full bg-[#BF416E] transition-transform duration-300 group-hover:scale-105"
				>
					<ClipboardPlus class="text-white" />
				</div>

				<span class=" text-sm text-[#475467]">Join Project</span>
			</a>

			<button
				onclick={(e) => e.currentTarget.querySelector('input')?.click()}
				class="group flex min-h-36 min-w-40 flex-col items-center justify-center gap-2 rounded-lg bg-[#EBEFFB] transition-colors duration-300 hover:bg-[#E2E5F1]"
			>
				<div
					class="flex aspect-square h-11 items-center justify-center rounded-full bg-[#4169E1] transition-transform duration-300 group-hover:scale-105"
				>
					<ImportIcon class="h-5 w-5 text-white" />
				</div>

				<span class=" text-sm text-[#475467]">{m['project.import_btn']()}</span>

				<input
					id="project-import"
					type="file"
					accept=".parquet"
					onchange={(e) => {
						e.preventDefault();
						handleImportProject(e, [...(e.currentTarget.files ?? [])]);
					}}
					multiple={false}
					class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
				/>
			</button>

			<a
				href="/template"
				class="group flex min-h-36 min-w-40 flex-col items-center justify-center gap-2 rounded-lg bg-[#90E9EF80] transition-colors duration-300 hover:bg-[#E2E5F1]"
			>
				<div
					class="flex aspect-square h-11 items-center justify-center rounded-full bg-[#019AA3] transition-transform duration-300 group-hover:scale-105"
				>
					<Compass class="text-white" />
				</div>

				<span class=" text-sm text-[#475467]">Browse Templates</span>
			</a>
		</div>

		<div class="flex min-h-0 flex-col px-6 pb-0 pt-6">
			<div class="sticky top-0 z-[1] flex flex-col gap-3 bg-[#F2F4F7] pb-1.5">
				<h2 class="pl-1 text-xl">{m['project.subheading']()}</h2>

				<div class="flex flex-col items-start justify-start gap-1 sm:flex-row">
					<div>
						<InputText
							oninput={debouncedSearchProjects}
							type="search"
							placeholder={m['project.search_placeholder']()}
							class="h-9 w-[16rem] pl-8 placeholder:not-italic placeholder:text-[#98A2B3]"
						>
							{#snippet leading()}
								{#if isLoadingSearch}
									<div class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
										<LoadingSpinner class="h-3" />
									</div>
								{:else}
									<SearchIcon
										class="pointer-events-none absolute left-3 top-1/2 h-3 -translate-y-1/2 text-[#667085]"
									/>
								{/if}
							{/snippet}
						</InputText>
					</div>

					<SorterSelect
						bind:sortOptions={$sortOptions}
						{sortableFields}
						refetchTables={refetchProjects}
						class="w-min min-w-[unset]"
					/>
				</div>
			</div>

			{#if !loadingProjectsError}
				<div
					style="grid-auto-rows: 240px;"
					class="grid grow grid-flow-row grid-cols-[minmax(15rem,1fr)] gap-4 px-1 pb-4 pt-1 sm:grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))]"
				>
					{#if isLoadingProjects}
						{#each Array(8) as _}
							<Skeleton
								class="flex flex-col items-center justify-center gap-2 rounded-lg bg-black/[0.09] data-dark:bg-white/[0.1]"
							/>
						{/each}
					{:else}
						{#each orgProjects ?? [] as project (project.id)}
							<a
								onclick={() => ($activeProject = project)}
								href="/project/{encodeURIComponent(project.id)}"
								title={project.id}
								class="flex flex-col rounded-lg border border-[#E5E5E5] bg-white transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-float data-dark:border-[#333] data-dark:bg-[#42464E]"
							>
								<div class="relative p-2">
									{#if projectsThumbs[project.id]}
										<!-- Temp fix for url -->
										<img
											src={projectsThumbs[project.id].replace('http://', 'https://')}
											class="h-28 w-full rounded-md object-cover"
											alt=""
										/>
									{:else if !project.cover_picture_url}
										<div class="flex h-28 items-center justify-center rounded-md bg-secondary">
											<Clipboard class="h-10 w-10 text-white" />
										</div>
									{:else}
										<div class="flex h-28 items-center justify-center">
											<LoadingSpinner class="h-4 w-4 text-secondary" />
										</div>
									{/if}

									<div class="absolute right-0 top-0 flex flex-wrap justify-end gap-1 p-3">
										{#each (project.tags ?? []).slice(0, 5) as tag, index}
											<span
												style="background-color: {tagColors[index % tagColors.length]};"
												class="select-none rounded-md px-1.5 py-[3px] text-xs text-white"
											>
												{tag}
											</span>
										{/each}

										{#if (project.tags ?? []).slice(5).length > 0}
											<span
												class="select-none rounded-md bg-black px-1.5 py-[3px] text-xs text-white"
											>
												+{(project.tags ?? []).slice(5).length}
											</span>
										{/if}
									</div>
								</div>

								<div class="flex grow items-start justify-between px-3 pb-1 pt-1">
									<div class="flex h-full flex-col items-start gap-1">
										<span class="line-clamp-2 text-[#475467] [word-break:break-word]">
											{project.name}
										</span>

										<p class="h-1 grow overflow-auto text-sm text-[#667085]">
											{project.description ?? ''}
										</p>
									</div>

									<DropdownMenu.Root>
										<DropdownMenu.Trigger>
											{#snippet child({ props })}
												<Button
													{...props}
													variant="ghost"
													onclick={(e) => e.preventDefault()}
													title="Project settings"
													class="aspect-square h-7 w-7 flex-[0_0_auto] -translate-y-1.5 translate-x-1.5 p-0"
												>
													<MoreVertIcon class="h-[18px] w-[18px]" />
												</Button>
											{/snippet}
										</DropdownMenu.Trigger>
										<DropdownMenu.Content data-testid="project-settings-dropdown" align="end">
											<DropdownMenu.Group>
												<DropdownMenu.Item
													onclick={() => (isEditingProjectName = project)}
													class="text-[#344054] data-[highlighted]:text-[#344054]"
												>
													<EditIcon class="mr-2 h-3.5 w-3.5" />
													<span>{m['project.settings_rename']()}</span>
												</DropdownMenu.Item>
												<ExportProjectButton>
													{#snippet children({ handleExportProject })}
														<DropdownMenu.Item
															onclick={() => handleExportProject(project.id)}
															class="text-[#344054] data-[highlighted]:text-[#344054]"
														>
															<ExportIcon class="mr-2 h-3.5" />
															<span>{m['project.settings_export']()}</span>
														</DropdownMenu.Item>
													{/snippet}
												</ExportProjectButton>
												<DropdownMenu.Separator />
												<DropdownMenu.Item
													onclick={() => (isDeletingProject = project.id)}
													class="text-destructive data-[highlighted]:text-destructive"
												>
													<Trash2 class="mr-2 h-3.5 w-3.5" />
													<span>{m['project.settings_delete']()}</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								</div>

								<div class="flex px-3 py-2">
									<span
										title={new Date(project.updated_at).toLocaleString(getLocale(), {
											month: 'long',
											day: 'numeric',
											year: 'numeric'
										})}
										class="line-clamp-1 text-xs text-[#98A2B3] data-dark:text-[#C9C9C9]"
									>
										{m['project.updated_at']()}
										<span class="text-[#667085]">
											{new Date(project.updated_at).toLocaleString(getLocale(), {
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
						<div class="mx-auto flex items-center justify-center p-4">
							<LoadingSpinner class="h-5 w-5 text-secondary" />
						</div>
					{/if}
				</div>
			{:else}
				<div class="mx-48 my-0 flex h-64 items-center justify-center">
					<span class="relative -top-[0.05rem] text-3xl font-extralight">
						{loadingProjectsError.status}
					</span>
					<div
						class="ml-4 flex min-h-10 items-center border-l border-[#ccc] pl-4 data-dark:border-[#666]"
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
<ProjectsThumbsFetch {orgProjects} bind:projectsThumbs />
