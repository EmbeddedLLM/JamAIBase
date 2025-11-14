<script lang="ts">
	import { page } from '$app/state';
	import type { ProjectMemberRead } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Dialog from '$lib/components/ui/dialog';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import { enhance } from '$app/forms';
	import { Button } from '$lib/components/ui/button';

	let {
		isRemovingUser = $bindable()
	}: { isRemovingUser: { open: boolean; value: ProjectMemberRead | null } } = $props();

	let loadingDeleteUser = $state(false);
</script>

<Dialog.Root
	bind:open={() => isRemovingUser.open, (v) => (isRemovingUser = { ...isRemovingUser, open: v })}
>
	<Dialog.Content
		data-testid="delete-proj-member-dialog"
		class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]"
	>
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<div class="flex flex-col items-start gap-2 p-8">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want to remove user
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{isRemovingUser.value?.user.name || isRemovingUser.value?.user_id}`
				</span>? This process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<form
				use:enhance={() => {
					loadingDeleteUser = true;

					return async ({ result, update }) => {
						if (result.type === 'failure') {
							const data = result.data as any;
							toast.error('Error removing user', {
								id: data?.err_message?.message || JSON.stringify(data),
								description: CustomToastDesc as any,
								componentProps: {
									description: data?.err_message?.message || JSON.stringify(data),
									requestID: data?.err_message?.request_id ?? ''
								}
							});
						} else if (result.type === 'success') {
							isRemovingUser = { ...isRemovingUser, open: false };
						}

						loadingDeleteUser = false;
						update({ reset: false });
					};
				}}
				method="POST"
				action="?/remove"
				class="flex gap-2 overflow-x-auto overflow-y-hidden"
			>
				<input type="hidden" name="project_id" value={page.params.project_id} />
				<input type="hidden" name="user_id" value={isRemovingUser.value?.user_id} />

				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					variant="destructive"
					loading={loadingDeleteUser}
					disabled={loadingDeleteUser}
					class="grow px-6"
				>
					Delete
				</Button>
			</form>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
