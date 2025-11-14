<script lang="ts">
	import { enhance } from '$app/forms';
	import type { User } from '$lib/types';

	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	let {
		isDeletingAccount = $bindable(),
		user
	}: { isDeletingAccount: boolean; user: User | undefined } = $props();

	let confirmEmail = $state('');
	let isLoadingDeleteAccount = $state(false);
</script>

<Dialog.Root
	bind:open={isDeletingAccount}
	onOpenChange={(e) => {
		if (!e) {
			confirmEmail = '';
		}
	}}
>
	<Dialog.Content
		data-testid="confirm-delete-account-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Delete account</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="deleteAccountForm"
			use:enhance={() => {
				isLoadingDeleteAccount = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error deleting account', {
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

					isLoadingDeleteAccount = false;
					update({ reset: false, invalidateAll: false });
				};
			}}
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			method="POST"
			action="?/delete-account"
			class="w-full grow overflow-auto"
		>
			<div class="flex h-full w-full grow flex-col gap-4 py-3">
				<p class="px-4 text-sm text-text/60 sm:px-6">
					Do you really want to delete your account
					<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
						`{user?.email}`
					</span>? This process cannot be undone.
				</p>

				<div class="flex w-full flex-col space-y-1 px-4 sm:px-6">
					<Label for="email" class="text-sm text-black">Enter email to confirm</Label>

					<InputText bind:value={confirmEmail} id="email" name="email" placeholder="Email" />
				</div>
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
					variant="destructive"
					type="submit"
					form="deleteAccountForm"
					loading={isLoadingDeleteAccount}
					disabled={isLoadingDeleteAccount || confirmEmail !== user?.email}
					class="relative grow px-6"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
