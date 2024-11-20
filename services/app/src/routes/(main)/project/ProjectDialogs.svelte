<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import type { Project } from '$lib/types';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	export let orgProjects: Project[];
	export let isAddingProject: boolean;
	export let isEditingProjectName: Project | null;
	export let isDeletingProject: string | null;
	export let refetchProjects: () => Promise<void>;

	let isLoadingAddProject = false;
	let newProjectForm: HTMLFormElement;

	let isLoadingSaveEdit = false;
	let editProjectForm: HTMLFormElement;

	let isLoadingDeleteProject = false;
	let confirmProjectName = '';
	let deleteProjectForm: HTMLFormElement;

	async function handleNewProject(e: SubmitEvent & { currentTarget: HTMLFormElement }) {
		if (isLoadingAddProject) return;
		isLoadingAddProject = true;

		const formData = new FormData(e.currentTarget);
		const project_name = formData.get('project_name') as string;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				name: project_name,
				organization_id: PUBLIC_IS_LOCAL !== 'false' ? 'default' : undefined
			})
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Failed to create project', {
				id: responseBody.err_message?.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.err_message?.message || JSON.stringify(responseBody),
					requestID: responseBody.err_message?.request_id
				}
			});
		} else {
			await refetchProjects();
			newProjectForm.reset();
			isAddingProject = false;
		}

		isLoadingAddProject = false;
	}

	async function handleSaveProjectName() {
		if (!isEditingProjectName || isLoadingSaveEdit) return;
		isLoadingSaveEdit = true;

		if (!editProjectForm.project_name.value.trim()) {
			toast.error('Project name is required', { id: 'project-name' });
			isLoadingSaveEdit = false;
			return;
		}

		if (editProjectForm.project_name.value === isEditingProjectName.name) {
			isLoadingSaveEdit = false;
			isEditingProjectName = null;
			return;
		}

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				id: isEditingProjectName.id,
				name: editProjectForm.project_name.value
			})
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error saving project name', {
				id: 'project-name-error',
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.err_message?.message || JSON.stringify(responseBody),
					requestID: responseBody.err_message?.request_id
				}
			});
		} else {
			await refetchProjects();
			editProjectForm.reset();
			isEditingProjectName = null;
		}

		isLoadingSaveEdit = false;
	}

	async function handleDeleteProject() {
		if (isLoadingDeleteProject) return;
		isLoadingDeleteProject = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${isDeletingProject}`,
			{
				method: 'DELETE'
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error deleting project', {
				id: responseBody.err_message?.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.err_message?.message || JSON.stringify(responseBody),
					requestID: responseBody.err_message?.request_id
				}
			});
		} else {
			await refetchProjects();
			deleteProjectForm?.reset();
			isDeletingProject = null;
		}

		confirmProjectName = '';
		isLoadingDeleteProject = false;
	}
</script>

<Dialog.Root
	open={!!isEditingProjectName}
	onOpenChange={(e) => {
		if (!e) {
			isEditingProjectName = null;
		}
	}}
>
	<Dialog.Content
		data-testid="rename-project-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Edit project name</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={editProjectForm}
			on:submit|preventDefault={handleSaveProjectName}
			class="grow w-full overflow-auto"
		>
			<div class="flex flex-col gap-2 px-4 sm:px-6 py-3 h-full w-full text-center">
				<label for="project_name" class="font-medium text-left text-xs sm:text-sm text-black">
					Project name*
				</label>

				<InputText
					value={isEditingProjectName?.name}
					id="project_name"
					name="project_name"
					placeholder="Required"
					required
				/>
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingSaveEdit} class="hidden">Save</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={() => editProjectForm.requestSubmit()}
					loading={isLoadingSaveEdit}
					disabled={isLoadingSaveEdit}
					class="relative grow px-6 rounded-full"
				>
					Save
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={isAddingProject}>
	<Dialog.Content data-testid="new-project-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>New project</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={newProjectForm}
			on:submit|preventDefault={handleNewProject}
			class="grow h-full w-full overflow-auto"
		>
			<div class="flex flex-col gap-2 px-4 sm:px-6 py-3 w-full text-center">
				<span class="font-medium text-left text-xs sm:text-sm text-black">Project name*</span>

				<InputText name="project_name" placeholder="Required" />
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingAddProject} class="hidden">Add</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
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
	{@const targetProject = orgProjects.find((project) => project.id === isDeletingProject)}
	<Dialog.Content
		data-testid="delete-project-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Delete project</Dialog.Header>

		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<form
			bind:this={deleteProjectForm}
			on:keydown={(event) => event.key === 'Enter' && event.preventDefault()}
			on:submit={handleDeleteProject}
			class="grow w-full overflow-auto"
		>
			<div class="grow flex flex-col gap-4 py-3 h-full w-full overflow-auto">
				<p class="px-4 sm:px-6 text-text/60 text-sm">
					Do you really want to delete project
					<span class="font-medium text-black data-dark:text-white [word-break:break-word]">
						`{targetProject?.name ?? isDeletingProject}`
					</span>? This process cannot be undone.
				</p>

				<div class="flex flex-col gap-2 px-4 sm:px-6 w-full text-center">
					<span class="font-medium text-left text-sm text-black">
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
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
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
