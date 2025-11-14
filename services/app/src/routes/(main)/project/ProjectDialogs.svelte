<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { page } from '$app/state';
	import type { Project } from '$lib/types';

	import { m } from '$lib/paraglide/messages';
	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { escapeHtmlText } from '$lib/utils';
	import { activeOrganization } from '$globalStore';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	interface Props {
		orgProjects: Project[];
		isAddingProject: boolean;
		isEditingProjectName: Project | null;
		isDeletingProject: string | null;
		refetchProjects: () => Promise<void>;
	}

	let {
		orgProjects,
		isAddingProject = $bindable(),
		isEditingProjectName = $bindable(),
		isDeletingProject = $bindable(),
		refetchProjects
	}: Props = $props();

	let isLoadingAddProject = $state(false);

	let isLoadingSaveEdit = $state(false);

	let isLoadingDeleteProject = $state(false);
	let confirmProjectName = $state('');

	async function handleNewProject(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();
		if (isLoadingAddProject) return;
		isLoadingAddProject = true;

		const formData = new FormData(e.currentTarget);
		const project_name = formData.get('project_name') as string;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/projects`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				name: project_name,
				organization_id: $activeOrganization?.id
			})
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Failed to create project', {
				id: responseBody?.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody?.message || JSON.stringify(responseBody),
					requestID: responseBody?.request_id
				}
			});
		} else {
			await refetchProjects();
			e.currentTarget?.reset();
			isAddingProject = false;
		}

		isLoadingAddProject = false;
	}

	async function handleSaveProjectName(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();
		if (!isEditingProjectName || isLoadingSaveEdit) return;
		isLoadingSaveEdit = true;

		if (!e.currentTarget?.project_name.value.trim()) {
			toast.error('Project name is required', { id: 'project-name' });
			isLoadingSaveEdit = false;
			return;
		}

		if (e.currentTarget.project_name.value === isEditingProjectName.name) {
			isLoadingSaveEdit = false;
			isEditingProjectName = null;
			return;
		}

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', isEditingProjectName.id]])}`,
			{
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					name: e.currentTarget.project_name.value
				})
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error saving project name', {
				id: 'project-name-error',
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody?.message || JSON.stringify(responseBody),
					requestID: responseBody?.request_id
				}
			});
		} else {
			await refetchProjects();
			e.currentTarget?.reset();
			isEditingProjectName = null;
		}

		isLoadingSaveEdit = false;
	}

	async function handleDeleteProject(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();
		if (isLoadingDeleteProject) return;
		isLoadingDeleteProject = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', isDeletingProject!]])}`,
			{
				method: 'DELETE'
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error deleting project', {
				id: responseBody?.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody?.message || JSON.stringify(responseBody),
					requestID: responseBody?.request_id
				}
			});
		} else {
			await refetchProjects();
			e.currentTarget?.reset();
			isDeletingProject = null;
		}

		confirmProjectName = '';
		isLoadingDeleteProject = false;
	}
</script>

<Dialog.Root bind:open={() => !!isEditingProjectName, () => (isEditingProjectName = null)}>
	<Dialog.Content
		data-testid="rename-project-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>{m['project.edit.heading']()}</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="editProjectForm"
			onsubmit={handleSaveProjectName}
			class="w-full grow overflow-auto py-3"
		>
			<div class="h-full w-full space-y-1 px-4 sm:px-6">
				<Label
					required
					for="project_name"
					class="text-left text-xs font-medium text-black sm:text-sm"
				>
					{m['project.edit.field_name']()}
				</Label>

				<InputText
					value={isEditingProjectName?.name}
					id="project_name"
					name="project_name"
					placeholder={m.field_required()}
					required
				/>
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingSaveEdit} class="hidden">{m.save()}</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">{m.cancel()}</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="editProjectForm"
					loading={isLoadingSaveEdit}
					disabled={isLoadingSaveEdit}
					class="relative grow px-6"
				>
					{m.save()}
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	bind:open={() => isAddingProject,
	(v) => {
		isAddingProject = v;
		page.url.searchParams.delete('new');
		history.replaceState(history.state, '', page.url);
	}}
>
	<Dialog.Content data-testid="new-project-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>{m['project.create.heading']()}</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="newProjectForm"
			onsubmit={handleNewProject}
			class="h-full w-full grow overflow-auto py-3"
		>
			<div class="space-y-1 px-4 sm:px-6">
				<Label required class="text-xs sm:text-sm">
					{m['project.create.field_name']()}
				</Label>

				<InputText required name="project_name" placeholder={m.field_required()} />
			</div>

			<!-- hidden submit -->
			<Button type="submit" disabled={isLoadingAddProject} class="hidden">{m.add()}</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">{m.cancel()}</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="newProjectForm"
					loading={isLoadingAddProject}
					disabled={isLoadingAddProject}
					class="relative grow px-6"
				>
					{m.create()}
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	bind:open={() => !!isDeletingProject, (v) => (isDeletingProject = null)}
	onOpenChange={(e) => {
		if (!e) {
			confirmProjectName = '';
		}
	}}
>
	{@const targetProject = orgProjects.find((project) => project.id === isDeletingProject)}
	<Dialog.Content
		data-testid="delete-project-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>{m['project.delete.heading']()}</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="deleteProjectForm"
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			onsubmit={handleDeleteProject}
			class="w-full grow overflow-auto"
		>
			<div class="flex h-full w-full grow flex-col gap-4 overflow-auto py-3">
				<p
					class="px-4 text-sm text-text/60 sm:px-6 [&>span]:font-medium [&>span]:text-black [&>span]:[word-break:break-word] [&>span]:data-dark:text-white"
				>
					{@html m['project.delete.text_content']({
						project_name: escapeHtmlText(targetProject?.name ?? isDeletingProject ?? '')
					})}
				</p>

				<div class="flex w-full flex-col gap-2 px-4 text-center sm:px-6">
					<span class="text-left text-sm font-medium text-black">
						{m['project.delete.text_confirm']({
							confirm_text: targetProject?.name ? 'name' : 'ID'
						})}
					</span>

					<InputText
						bind:value={confirmProjectName}
						name="project_name"
						placeholder={m['project.delete.field_confirm']({
							confirm_text: targetProject?.name ? 'name' : 'ID'
						})}
					/>
				</div>
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">{m.cancel()}</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="deleteProjectForm"
					variant="destructive"
					loading={isLoadingDeleteProject}
					disabled={isLoadingDeleteProject ||
						confirmProjectName !== (targetProject?.name ?? isDeletingProject)}
					class="relative grow px-6"
				>
					{m.delete()}
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
