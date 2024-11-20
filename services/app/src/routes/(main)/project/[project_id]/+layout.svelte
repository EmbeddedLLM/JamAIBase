<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { activeProject, loadingProjectData, showLoadingOverlay } from '$globalStore';
	import { textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';
	import type { Project } from '$lib/types';

	import ProjectDialogs from '../ProjectDialogs.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ArrowBackIcon from '$lib/icons/ArrowBackIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';

	let isEditingProjectName: Project | null = null;
	let isDeletingProject: string | null = null;

	async function handleExportProject() {
		if (PUBLIC_IS_LOCAL === 'false') {
			window
				.open(
					`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${$page.params.project_id}/export`,
					'_blank'
				)
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${$page.params.project_id}/export`
			);

			if (response.ok) {
				const contentDisposition = response.headers.get('content-disposition');
				const responseBody = await response.blob();
				textToFileDownload(
					/filename="(?<filename>.*)"/.exec(contentDisposition ?? '')?.groups?.filename ||
						`${$activeProject?.id}.arrow`,
					responseBody
				);
			} else {
				const responseBody = await response.json();
				logger.error(`PROJECT_EXPORT_PROJECT`, responseBody);
				console.error(responseBody);
				toast.error('Failed to export project', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}

			$showLoadingOverlay = false;
		}
	}

	let tabHighlightPos = '';
	$: if ($page.route.id?.endsWith('/project/[project_id]/action-table')) {
		tabHighlightPos = 'left-0 ';
	} else if ($page.route.id?.endsWith('/project/[project_id]/knowledge-table')) {
		tabHighlightPos = 'left-1/3';
	} else if ($page.route.id?.endsWith('/project/[project_id]/chat-table')) {
		tabHighlightPos = 'left-2/3';
	}
</script>

<section class="relative flex flex-col !h-screen">
	<div class="relative flex flex-col md:pt-3 pb-0 md:pr-6">
		<div class="flex items-center gap-2 pl-8 md:pr-0 pr-8 pt-0.5 text-[#344054]">
			<a href="/project" class="[all:unset] !hidden sm:!block">
				<Button
					variant="ghost"
					title="Back to projects"
					class="flex-[0_0_auto] flex items-center justify-center p-0 h-8 aspect-square"
				>
					<ArrowBackIcon class="h-7" />
				</Button>
			</a>

			<h1 class="text-xl line-clamp-1 break-all">
				{$activeProject?.name ??
					($loadingProjectData.loading
						? 'Loading...'
						: $loadingProjectData.error ?? $page.params.project_id)}
			</h1>

			<DropdownMenu.Root>
				<DropdownMenu.Trigger asChild let:builder>
					<Button
						variant="ghost"
						on:click={(e) => e.preventDefault()}
						builders={[builder]}
						title="Project settings"
						class="flex-[0_0_auto] flex items-center justify-center p-0 h-8 aspect-square"
					>
						<HamburgerIcon class="h-5" />
					</Button>
				</DropdownMenu.Trigger>
				<DropdownMenu.Content alignOffset={72} transitionConfig={{ x: -5, y: -5 }} class="min-w-44">
					<DropdownMenu.Group>
						<DropdownMenu.Item
							on:click={() => (isEditingProjectName = $activeProject)}
							class="text-[#344054] data-[highlighted]:text-[#344054]"
						>
							<EditIcon class="h-3.5 w-3.5 mr-2" />
							<span>Rename</span>
						</DropdownMenu.Item>
						<DropdownMenu.Item
							on:click={() => {
								navigator.clipboard.writeText($page.params.project_id ?? '');
								toast.success('Project ID copied to clipboard', { id: 'project-id-copied' });
							}}
						>
							<svg
								viewBox="0 0 10 10"
								fill="none"
								xmlns="http://www.w3.org/2000/svg"
								class="h-3.5 mr-2"
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
							on:click={() => (isDeletingProject = $page.params.project_id)}
							class="text-destructive data-[highlighted]:text-destructive"
						>
							<Trash_2 class="h-3.5 w-3.5 mr-2" />
							<span>Delete project</span>
						</DropdownMenu.Item>
					</DropdownMenu.Group>
				</DropdownMenu.Content>
			</DropdownMenu.Root>

			<Button
				title="Export project"
				on:click={handleExportProject}
				class="flex items-center gap-2 ml-auto p-0 md:px-3.5 h-8 text-[#475467] bg-[#F2F4F7] hover:bg-[#E4E7EC] active:bg-[#E4E7EC]  aspect-square md:aspect-auto"
			>
				<ExportIcon class="h-3.5" />

				<span class="hidden md:block">Export</span>
			</Button>
		</div>

		<div
			data-testid="table-type-nav"
			class="relative grid grid-cols-[repeat(3,minmax(6rem,1fr))] sm:grid-cols-[repeat(3,minmax(8.5rem,1fr))] items-end mt-2 sm:mt-3 mx-0 sm:mx-8 w-full sm:w-fit text-xs sm:text-sm overflow-auto"
		>
			<a
				href="/project/{$page.params.project_id}/action-table"
				class="px-0 sm:px-4 py-2 {$page.route.id?.endsWith('/project/[project_id]/action-table')
					? 'text-[#344054] font-medium'
					: 'text-[#98A2B3]'} text-center transition-colors"
			>
				Action Table
			</a>

			<a
				href="/project/{$page.params.project_id}/knowledge-table"
				class="px-0 sm:px-4 py-2 {$page.route.id?.endsWith('/project/[project_id]/knowledge-table')
					? 'text-[#344054] font-medium'
					: 'text-[#98A2B3]'} text-center transition-colors"
			>
				Knowledge Table
			</a>

			<a
				href="/project/{$page.params.project_id}/chat-table"
				class="px-0 sm:px-4 py-2 {$page.route.id?.endsWith('/project/[project_id]/chat-table')
					? 'text-[#344054] font-medium'
					: 'text-[#98A2B3]'} text-center transition-colors"
			>
				Chat Table
			</a>

			<div
				class="absolute bottom-0 {tabHighlightPos} h-[3px] w-1/3 bg-secondary transition-[left]"
			/>
		</div>

		<hr
			class="absolute bottom-0 left-0 w-[calc(100%)] border-[#E5E5E5] data-dark:border-[#0D0E11]"
		/>
	</div>

	<slot />
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
