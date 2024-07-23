<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import Trash_2 from 'lucide-svelte/icons/trash-2';
	import { invalidateAll } from '$app/navigation';

	import BreadcrumbsBar from '../BreadcrumbsBar.svelte';
	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import * as Dialog from '$lib/components/ui/dialog';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';

	export let data;
	$: ({ organizationData } = data);

	let isAddingProject = false;
	let isLoadingAddProject = false;
	let newProjectForm: HTMLFormElement;

	let isDeletingProject: string | null = null;
	let isLoadingDeleteProject = false;
	let confirmProjectName = '';
	let deleteProjectForm: HTMLFormElement;

	async function handleNewProject(e: SubmitEvent & { currentTarget: HTMLFormElement }) {
		if (isLoadingAddProject) return;
		isLoadingAddProject = true;

		const formData = new FormData(e.currentTarget);
		const project_name = formData.get('project_name') as string;

		const response = await fetch(`/api/projects`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				project_name
			})
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Failed to create project', {
				description: responseBody.err_message?.message || JSON.stringify(responseBody)
			});
		} else {
			invalidateAll();
			newProjectForm.reset();
			isAddingProject = false;
		}

		isLoadingAddProject = false;
	}

	async function handleDeleteProject() {
		if (isLoadingDeleteProject) return;
		isLoadingDeleteProject = true;

		const response = await fetch(`/api/projects/${isDeletingProject}`, {
			method: 'DELETE'
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error deleting project', {
				description: responseBody.err_message?.message || JSON.stringify(responseBody)
			});
			isLoadingDeleteProject = false;
		} else {
			invalidateAll();
			deleteProjectForm.reset();
			isDeletingProject = null;
		}
	}
</script>

<svelte:head>
	<title>Projects</title>
</svelte:head>

<section class="relative flex flex-col !h-screen">
	<BreadcrumbsBar />

	<div class="relative flex flex-col gap-2 p-6 pt-0 pb-0">
		<div class="flex items-center gap-1 -translate-x-2.5">
			<div class="flex items-center justify-center ml-3 p-1.5 rounded-md">
				<AssignmentIcon class="h-6 text-text" />
			</div>
			<h1 class="font-medium text-xl">Projects</h1>
		</div>
	</div>

	<div class="grid grid-cols-[12rem_minmax(0,_auto)] gap-3 pt-6 pb-0 pl-7 pr-6 min-h-0">
		<div class="flex pt-1">
			<button
				on:click={() => (isAddingProject = true)}
				class="grow flex flex-col items-center justify-center gap-2 h-36 bg-secondary/[0.12] rounded-lg"
			>
				<div class="flex items-center justify-center h-8 bg-secondary rounded-full aspect-square">
					<AddIcon class="h-4 w-4 text-white" />
				</div>

				<span class="font-medium text-sm"> New Project </span>
			</button>
		</div>

		<div
			style="grid-auto-rows: 144px;"
			class="grid grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 3xl:grid-cols-5 grid-flow-row gap-4 pt-1 pb-4 px-1 overflow-auto"
		>
			{#each organizationData?.projects ?? [] as project (project.id)}
				<a
					href={`/project/${project.id}`}
					title={project.id}
					class="flex flex-col bg-white data-dark:bg-[#42464E] border border-[#E5E5E5] data-dark:border-[#333] rounded-lg hover:-translate-y-0.5 hover:shadow-float transition-[transform,box-shadow]"
				>
					<div
						class="grow flex items-start justify-between p-3 border-b border-[#E5E5E5] data-dark:border-[#333]"
					>
						<div class="flex items-start gap-1.5">
							<AssignmentIcon class="flex-[0_0_auto] h-5 w-5 text-secondary" />
							<span class="font-medium text-sm break-all line-clamp-2">{project.name}</span>
						</div>

						<DropdownMenu.Root>
							<DropdownMenu.Trigger asChild let:builder>
								<Button
									on:click={(e) => e.preventDefault()}
									builders={[builder]}
									variant="ghost"
									title="Project settings"
									class="p-0 h-7 w-7 aspect-square rounded-full translate-x-1.5 -translate-y-1"
								>
									<MoreVertIcon class="h-[18px] w-[18px]" />
								</Button>
							</DropdownMenu.Trigger>
							<DropdownMenu.Content alignOffset={-50} transitionConfig={{ x: 5, y: -5 }}>
								<DropdownMenu.Group>
									<DropdownMenu.Item on:click={() => (isDeletingProject = project.id)}>
										<Trash_2 class="h-4 w-4 mr-2 mb-[2px]" />
										<span>Delete project</span>
									</DropdownMenu.Item>
								</DropdownMenu.Group>
							</DropdownMenu.Content>
						</DropdownMenu.Root>
					</div>

					<div class="flex p-3">
						<span
							title={new Date(project.updated_at).toLocaleString(undefined, {
								month: 'long',
								day: 'numeric',
								year: 'numeric'
							})}
							class="text-xs text-[#999] data-dark:text-[#C9C9C9] line-clamp-1"
						>
							Updated at: {new Date(project.updated_at).toLocaleString(undefined, {
								month: 'long',
								day: 'numeric',
								year: 'numeric'
							})}
						</span>
					</div>
				</a>
			{/each}
		</div>
	</div>
</section>

<Dialog.Root bind:open={isAddingProject}>
	<Dialog.Content class="max-h-[90vh] min-w-[35rem]">
		<Dialog.Header>New project</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={newProjectForm}
			on:submit|preventDefault={handleNewProject}
			class="grow py-3 h-full w-full overflow-auto"
		>
			<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Project name
				</span>

				<InputText name="project_name" placeholder="Enter project name" />
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingAddProject} class="hidden">Add</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={() => newProjectForm.requestSubmit()}
					loading={isLoadingAddProject}
					disabled={isLoadingAddProject}
					class="relative grow px-6 rounded-full"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	open={!!isDeletingProject}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingProject = null;
			confirmProjectName = '';
		}
	}}
>
	{@const targetProject = organizationData?.projects.find(
		(project) => project.id === isDeletingProject
	)}
	<Dialog.Content class="max-h-[90vh] min-w-[35rem]">
		<Dialog.Header>Delete project</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={deleteProjectForm}
			on:keydown={(event) => event.key === 'Enter' && event.preventDefault()}
			on:submit={handleDeleteProject}
			class="grow w-full overflow-auto"
		>
			<div class="grow flex flex-col gap-2 py-3 h-full w-full overflow-auto">
				<p class="px-6 pl-8 text-text/60 text-sm">
					Do you really want to delete project
					<span class="font-medium text-black data-dark:text-white">
						`{targetProject?.name ?? isDeletingProject}`
					</span>? This process cannot be undone.
				</p>

				<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
					<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Enter project {targetProject?.name ? 'name' : 'ID'} to confirm
					</span>

					<InputText
						bind:value={confirmProjectName}
						name="project_name"
						placeholder="Project name"
					/>
				</div>
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					variant="destructive"
					on:click={() => deleteProjectForm.requestSubmit()}
					loading={isLoadingDeleteProject}
					disabled={isLoadingDeleteProject ||
						confirmProjectName !== (targetProject?.name ?? isDeletingProject)}
					class="relative grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
