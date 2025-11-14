<script lang="ts">
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import { userRoles } from '$lib/constants';
	import type { OrgMemberRead } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	let {
		isInvitingUser = $bindable(),
		organizationMembers
	}: { isInvitingUser: boolean; organizationMembers: OrgMemberRead[] } = $props();

	let isLoadingInvite = $state(false);

	let userId = $state('');
	let selectedUserRoleInvite = $state<(typeof userRoles)[number]>('GUEST');
	let inviteValidity = $state('7');

	let showCodeDialog = $state<string | null>(null);
</script>

<Dialog.Root bind:open={isInvitingUser}>
	<Dialog.Content data-testid="invite-user-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Add member</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="inviteUserProj"
			use:enhance={() => {
				isLoadingInvite = true;

				return async ({ result, update }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error('Error inviting user to organization', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						await update({ reset: false });
						userId = '';
						isInvitingUser = false;
						if ((result.data as any).id) {
							showCodeDialog = (result.data as any).id;
						} else {
							toast.success('Invite userId sent!', { id: 'invite-sent' });
						}
					}

					isLoadingInvite = false;
				};
			}}
			method="POST"
			action="?/invite"
			class="flex grow flex-col gap-3 overflow-auto py-3"
		>
			<input type="hidden" name="project_id" value={page.params.project_id} />

			<div class="flex w-full flex-col space-y-1 px-4 text-center sm:px-6">
				<Label required for="user_id" class="text-left text-xs font-medium text-black sm:text-sm">
					Organization member
				</Label>
				<input
					bind:value={userId}
					type="hidden"
					placeholder="Required"
					id="user_id"
					name="user_id"
				/>

				<Select.Root type="single" bind:value={userId}>
					<Select.Trigger
						class="flex h-[38px] min-w-full items-center justify-between gap-2 pl-3 pr-2 sm:gap-8"
					>
						{#snippet children()}
							{@const selectedOrgMember = organizationMembers.find((v) => v.user_id === userId)}
							<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
								{#if userId}
									{#if selectedOrgMember}
										{selectedOrgMember.user.name}&nbsp;&nbsp;–&nbsp;
										<span class="italic">
											{selectedOrgMember.user.email}
										</span>
									{:else}
										{userId}
									{/if}
								{:else}
									Select organization member
								{/if}
							</span>
						{/snippet}
					</Select.Trigger>
					<Select.Content class="max-h-64 overflow-y-auto">
						{#each organizationMembers as organizationMember}
							<Select.Item
								value={organizationMember.user_id}
								label="{organizationMember.user.name} - {organizationMember.user.email}"
								class="flex cursor-pointer gap-1"
							>
								{organizationMember.user.name}&nbsp;&nbsp;–&nbsp;
								<span class="italic">
									{organizationMember.user.email}
								</span>
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			<div class="flex w-full flex-col space-y-1 px-4 text-center sm:px-6">
				<Label required for="user_role" class="text-left text-xs font-medium text-black sm:text-sm">
					User role
				</Label>
				<Select.Root name="user_role" type="single" bind:value={selectedUserRoleInvite}>
					<Select.Trigger
						class="h-10 min-w-full border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e]"
					>
						<span class="line-clamp-1 whitespace-nowrap text-left font-normal capitalize">
							{selectedUserRoleInvite}
						</span>
					</Select.Trigger>
					<Select.Content class="max-h-64 overflow-y-auto">
						{#each userRoles as roleType}
							<Select.Item
								value={roleType}
								label={roleType}
								class="flex cursor-pointer justify-between gap-10 capitalize"
							>
								{roleType}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			<!-- <div class="flex w-full flex-col space-y-1 px-4 text-center sm:px-6">
				<Label
					required
					for="valid_days"
					class="text-left text-xs font-medium text-black sm:text-sm"
				>
					Validity
				</Label>
				<Select.Root name="valid_days" type="single" bind:value={inviteValidity}>
					<Select.Trigger
						class="h-10 min-w-full border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e]"
					>
						<span class="line-clamp-1 whitespace-nowrap text-left font-normal capitalize">
							{inviteValidity} days
						</span>
					</Select.Trigger>
					<Select.Content class="max-h-64 overflow-y-auto">
						{#each ['1', '2', '3', '4', '5', '6', '7'] as daysValid}
							<Select.Item
								value={daysValid}
								label="{daysValid} days"
								class="flex cursor-pointer justify-between gap-10 capitalize"
							>
								{daysValid} days
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div> -->
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
					form="inviteUserProj"
					loading={isLoadingInvite}
					disabled={isLoadingInvite}
					class="relative grow px-6"
				>
					Invite
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={() => !!showCodeDialog, () => (showCodeDialog = null)}>
	<Dialog.Content data-testid="invite-user-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Invite code</Dialog.Header>

		<div class="w-full grow overflow-auto">
			<div class="h-full w-full grow overflow-auto px-6 py-3">
				<p class="mb-2 text-sm font-medium">Invitation Code:</p>
				<div class="flex items-center gap-2">
					<code class="flex-1 rounded bg-gray-100 p-2 font-mono">{showCodeDialog}</code>
					<Button
						variant="outline"
						onclick={async () => {
							if (showCodeDialog) {
								await navigator.clipboard.writeText(showCodeDialog);
								toast.success('Invite code copied to clipboard!');
							}
						}}
						class="rounded-lg"
					>
						Copy
					</Button>
				</div>
				<p class="mt-2 text-sm text-gray-500">Share this code with the user you want to invite.</p>
			</div>
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
