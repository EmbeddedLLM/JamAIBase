<script lang="ts">
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { activeProject, loadingProjectData } from '$globalStore';
	import type { Project } from '$lib/types';

	import ProjectDialogs from '../ProjectDialogs.svelte';
	import ExportProjectButton from '../ExportProjectButton.svelte';
	import { toast } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();

	const tabItems = [
		// {
		// 	title: 'Overview',
		// 	href: `/project/${page.params.project_id}/overview`,
		// 	route: '/(main)/project/[project_id]/overview'
		// },
		{
			title: 'Action Table',
			href: `/project/${page.params.project_id}/action-table`,
			route: '/(main)/project/[project_id]/action-table'
		},
		{
			title: 'Knowledge Table',
			href: `/project/${page.params.project_id}/knowledge-table`,
			route: '/(main)/project/[project_id]/knowledge-table'
		},
		{
			title: 'Chat Table',
			href: `/project/${page.params.project_id}/chat-table`,
			route: '/(main)/project/[project_id]/chat-table'
		},
		{
			title: 'Members',
			href: `/project/${page.params.project_id}/members`,
			route: '/(main)/project/[project_id]/members'
		}
	];

	let isEditingProjectName: Project | null = $state(null);
	let isDeletingProject: string | null = $state(null);

	let tabHighlightPos = $derived(
		(tabItems.findIndex((t) => page.route.id === t.route) / tabItems.length) * 100
	);
</script>

<section class="relative flex !h-screen flex-col">
	<div class="relative flex flex-col pb-0 md:pr-6 md:pt-3">
		<div class="flex items-center gap-2 pl-8 pr-8 pt-0.5 text-[#344054] md:pr-0">
			<Button
				variant="ghost"
				href="/project"
				title="Back to projects"
				class="hidden aspect-square h-8 flex-[0_0_auto] items-center justify-center p-0 sm:flex"
			>
				<ArrowBackIcon class="h-7" />
			</Button>

			<h1 class="line-clamp-1 break-all text-xl">
				{$activeProject?.name ??
					($loadingProjectData.loading
						? 'Loading...'
						: ($loadingProjectData.error ?? page.params.project_id))}
			</h1>

			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button
							{...props}
							variant="ghost"
							onclick={(e) => e.preventDefault()}
							title="Project settings"
							class="flex aspect-square h-8 flex-[0_0_auto] items-center justify-center p-0"
						>
							<HamburgerIcon class="h-5" />
						</Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" class="min-w-44">
					<DropdownMenu.Group>
						<DropdownMenu.Item
							onclick={() => (isEditingProjectName = $activeProject)}
							class="text-[#344054] data-[highlighted]:text-[#344054]"
						>
							<EditIcon class="mr-2 h-3.5 w-3.5" />
							<span>Rename project</span>
						</DropdownMenu.Item>
						<DropdownMenu.Item
							onclick={() => {
								navigator.clipboard.writeText(page.params.project_id ?? '');
								toast.success('Project ID copied to clipboard', { id: 'project-id-copied' });
							}}
							class="text-[#344054] data-[highlighted]:text-[#344054]"
						>
							<svg
								viewBox="0 0 10 10"
								fill="none"
								xmlns="http://www.w3.org/2000/svg"
								class="mr-2 h-3.5"
							>
								<path
									d="M3.15445 8.99962H8.38522C8.72509 8.99962 9.0006 8.72412 9.0006 8.38424V3.15347C9.0006 2.8136 8.72509 2.53809 8.38522 2.53809H3.15445C2.81458 2.53809 2.53906 2.8136 2.53906 3.15347V8.38424C2.53906 8.72412 2.81458 8.99962 3.15445 8.99962Z"
									stroke="currentColor"
									stroke-width="0.8"
									stroke-linecap="round"
									stroke-linejoin="round"
								/>
								<path
									d="M1 7.15385V1.61538C1 1.45217 1.06484 1.29565 1.18024 1.18024C1.29565 1.06484 1.45217 1 1.61538 1H7.15385"
									stroke="currentColor"
									stroke-width="0.8"
									stroke-linecap="round"
									stroke-linejoin="round"
								/>
							</svg>

							<span>Copy project ID</span>
						</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item
							onclick={() => (isDeletingProject = page.params.project_id ?? null)}
							class="text-destructive data-[highlighted]:text-destructive"
						>
							<Trash_2 class="mr-2 h-3.5 w-3.5" />
							<span>Delete project</span>
						</DropdownMenu.Item>
					</DropdownMenu.Group>
				</DropdownMenu.Content>
			</DropdownMenu.Root>

			<ExportProjectButton>
				{#snippet children({ handleExportProject })}
					<Button
						variant="action"
						title="Export project"
						onclick={() => handleExportProject()}
						class="ml-auto flex aspect-square h-8 items-center gap-2 p-0 md:aspect-auto md:px-3.5"
					>
						<ExportIcon class="h-3.5" />

						<span class="hidden md:block">Export project</span>
					</Button>
				{/snippet}
			</ExportProjectButton>
		</div>

		<div
			data-testid="table-type-nav"
			style="grid-template-columns: repeat({tabItems.length}, minmax(6rem, 1fr));"
			class="relative mx-0 mt-2 grid w-full items-end overflow-auto text-xs sm:mt-3 sm:w-fit sm:grid-cols-[repeat(3,minmax(8.5rem,1fr))] sm:text-sm md:mx-8"
		>
			{#each tabItems as { title, href, route }}
				<a
					{href}
					class="px-0 py-2 font-medium sm:px-4 {page.route.id?.endsWith(route)
						? 'text-[#344054]'
						: 'text-[#98A2B3]'} text-center transition-colors"
				>
					{title}
				</a>
			{/each}

			<div
				style="width: {(1 / tabItems.length) * 100}%; left: {tabHighlightPos}%;"
				class="absolute bottom-0 h-[3px] bg-secondary transition-[left]"
			></div>
		</div>

		<hr
			class="absolute bottom-0 left-0 w-[calc(100%)] border-[#E5E5E5] data-dark:border-[#0D0E11]"
		/>
	</div>

	{@render children?.()}
</section>

{#if $activeProject}
	<ProjectDialogs
		isAddingProject={false}
		bind:isEditingProjectName
		bind:isDeletingProject
		orgProjects={[$activeProject]}
		refetchProjects={async () => {
			if (isEditingProjectName) {
				location.reload();
			} else if (isDeletingProject) {
				await goto('/project');
			}
		}}
	/>
{/if}
