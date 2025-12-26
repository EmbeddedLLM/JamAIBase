<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { XIcon } from '@lucide/svelte';
	import { page } from '$app/state';
	import { activeProject } from '$globalStore';
	import { tagColors } from '$lib/constants';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import InputText from '$lib/components/InputText.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	let { isEditingProjectProfile = $bindable() }: { isEditingProjectProfile: boolean } = $props();

	let tagName = $state('');
	let editProjectTags = $state<string[]>($activeProject?.tags ?? []);
	let isLoadingEditProfile = $state(false);

	async function handleEditProfile(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();

		if (isLoadingEditProfile) return;
		isLoadingEditProfile = true;

		const formData = new FormData(e.currentTarget);
		const project_name = formData.get('project_name') as string;
		const project_subtitle = formData.get('project_subtitle') as string;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', page.params.project_id ?? '']])}`,
			{
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					name: project_name,
					description: project_subtitle,
					tags: editProjectTags
				})
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Failed to save project profile', {
				id: responseBody?.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody?.message || JSON.stringify(responseBody),
					requestID: responseBody?.request_id
				}
			});
		} else {
			location.reload();
			e.currentTarget?.reset();
			isEditingProjectProfile = false;
		}

		isLoadingEditProfile = false;
	}
</script>

<Dialog.Root
	bind:open={isEditingProjectProfile}
	onOpenChange={(e) => {
		editProjectTags = $activeProject?.tags ?? [];
		tagName = '';
	}}
>
	<Dialog.Content
		data-testid="edit-project-info-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Edit Profile</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="editProjectProfileForm"
			onsubmit={handleEditProfile}
			class="h-full w-full grow overflow-auto py-3"
		>
			<div class="space-y-1 px-4 sm:px-6">
				<Label required for="project_name" class="text-xs sm:text-sm">Project Name</Label>

				<InputText
					required
					id="project_name"
					value={$activeProject?.name}
					name="project_name"
					placeholder="Required"
				/>
			</div>

			<div class="mt-4 space-y-1 px-4 sm:px-6">
				<Label for="project_subtitle" class="text-xs sm:text-sm">Project Description</Label>

				<InputText
					id="project_subtitle"
					value={$activeProject?.description}
					name="project_subtitle"
				/>
			</div>

			<div class="mt-4 space-y-1 px-4 sm:px-6">
				<Label for="project_tags" class="text-xs sm:text-sm">Tags</Label>

				<div class="flex items-center gap-2">
					<InputText id="project_tags" name="project_tags" bind:value={tagName} />

					<Button
						type="button"
						disabled={!tagName}
						onclick={() => {
							if (!tagName) return;
							editProjectTags = [...editProjectTags, tagName];
							tagName = '';
						}}
						class="flex items-center gap-2"
					>
						<AddIcon class="mb-px h-3.5 w-3.5" />
						Add
					</Button>
				</div>

				{#if editProjectTags.length > 0}
					<div class="flex flex-wrap gap-1 pt-1">
						{#each editProjectTags as tag, index}
							<span
								style="background-color: {tagColors[index % tagColors.length]};"
								class="flex select-none items-center gap-1 rounded-md px-1.5 py-[3px] text-xs text-white"
							>
								{tag}

								<button
									type="button"
									onclick={() => (editProjectTags = editProjectTags.filter((_, i) => i !== index))}
								>
									<XIcon class="h-3.5 w-3.5" />
								</button>
							</span>
						{/each}
					</div>
				{/if}
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="editProjectProfileForm"
					loading={isLoadingEditProfile}
					disabled={isLoadingEditProfile}
					class="relative grow px-6"
				>
					Save changes
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
