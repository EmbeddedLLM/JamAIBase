<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/state';
	import { activeProject } from '$globalStore';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	let { isEditingProjectReadme = $bindable() }: { isEditingProjectReadme: boolean } = $props();

	let isLoadingEditReadme = $state(false);

	async function handleSaveProjecReadme(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();

		if (isLoadingEditReadme) return;
		isLoadingEditReadme = true;

		const formData = new FormData(e.currentTarget);
		const project_readme = formData.get('project_readme') as string;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', page.params.project_id ?? '']])}`,
			{
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					meta: {
						readme: project_readme
					}
				})
			}
		);
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Failed to edit project README', {
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
			isEditingProjectReadme = false;
		}

		isLoadingEditReadme = false;
	}
</script>

<Dialog.Root bind:open={isEditingProjectReadme}>
	<Dialog.Content
		data-testid="edit-project-readme-dialog"
		class="h-[80vh] w-[clamp(0px,60rem,100%)]"
	>
		<Dialog.Header>Edit README</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="editProjectReadmeForm"
			onsubmit={handleSaveProjecReadme}
			class="h-full w-full grow overflow-auto p-3"
		>
			<textarea
				value={($activeProject?.meta?.readme as string) ?? ''}
				name="project_readme"
				class="h-full w-full resize-none border bg-[#F2F4F7] p-2 text-sm"
			></textarea>
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
					form="editProjectReadmeForm"
					loading={isLoadingEditReadme}
					disabled={isLoadingEditReadme}
					class="relative grow px-6"
				>
					Save changes
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
