<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { Dialog as DialogPrimitive } from 'bits-ui';

	import BreadcrumbsBar from '../BreadcrumbsBar.svelte';
	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	export let data;
	$: ({ organizationData } = data);

	let isAddingProject = false;
	let isLoadingAddProject = false;
	let newProjectForm: HTMLFormElement;

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
</script>

<svelte:head>
	<title>Projects</title>
</svelte:head>

<section class="relative flex flex-col !h-screen">
	<BreadcrumbsBar />

	<div class="relative flex flex-col gap-2 p-6 pt-0 pb-0">
		<div class="flex items-center gap-2 -translate-x-2.5">
			<div class="flex items-center justify-center ml-3 p-1.5 bg-secondary/[0.12] rounded-md">
				<AssignmentIcon class="h-[26px] text-secondary" />
			</div>
			<h1 class="font-medium text-xl">Projects</h1>
		</div>
	</div>

	<div class="grid grid-cols-[12rem_minmax(0,_auto)] gap-4 p-7 pb-0 min-h-0">
		<div class="flex">
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
			class="grid grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 3xl:grid-cols-5 grid-flow-row gap-4 pb-4 overflow-auto"
		>
			{#each organizationData?.projects ?? [] as project (project.id)}
				<a
					href={`/project/${project.id}`}
					title={project.id}
					class="flex flex-col border border-[#E5E5E5] data-dark:border-[#333] rounded-lg"
				>
					<div class="grow flex items-start p-3 border-b border-[#E5E5E5] data-dark:border-[#333]">
						<div class="flex items-start gap-1.5">
							<AssignmentIcon class="flex-[0_0_auto] h-5 w-5 text-secondary" />
							<span class="font-medium text-sm break-all line-clamp-2">{project.name}</span>
						</div>
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
