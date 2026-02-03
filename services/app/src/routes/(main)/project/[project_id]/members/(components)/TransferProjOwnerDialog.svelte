<script lang="ts">
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import type { ProjectMemberRead } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import WarningIcon from '$lib/icons/WarningIcon.svelte';

	let { isDeifyingUser = $bindable() }: { isDeifyingUser: ProjectMemberRead | null } = $props();

	let loadingDeifyingUser = $state(false);
</script>

<Dialog.Root bind:open={() => !!isDeifyingUser, () => (isDeifyingUser = null)}>
	<Dialog.Content class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]">
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="deifyingUserForm"
			use:enhance={() => {
				loadingDeifyingUser = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error transferring project ownership', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else {
						return location.reload();
					}

					loadingDeifyingUser = false;
					update({ reset: false, invalidateAll: false });
				};
			}}
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			method="POST"
			action="?/deify"
			class="flex flex-col items-start gap-2 p-8 pb-10"
		>
			<input type="hidden" name="project_id" value={page.params.project_id} />
			<input type="hidden" name="user_id" value={isDeifyingUser?.user_id} />

			<WarningIcon class="mb-1 h-10 text-warning" />
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want transfer ownership of this project to user
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{isDeifyingUser?.user.name || isDeifyingUser?.user.email || isDeifyingUser?.user_id}`
				</span>?
			</p>
		</form>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					variant="warning"
					type="submit"
					form="deifyingUserForm"
					loading={loadingDeifyingUser}
					disabled={loadingDeifyingUser}
					class="grow px-6"
				>
					Transfer
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
