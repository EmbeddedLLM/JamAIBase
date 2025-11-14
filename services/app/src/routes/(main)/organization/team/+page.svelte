<script lang="ts">
	import { enhance } from '$app/forms';
	import lowerCase from 'lodash/lowerCase';
	import { isThisYear } from 'date-fns';
	import { activeOrganization } from '$globalStore';
	import { userRoles } from '$lib/constants';
	import type { OrgMemberRead } from '$lib/types';

	import OrgInviteDialog from './OrgInviteDialog.svelte';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import DeleteIcon from '$lib/icons/DeleteIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import PersonAddIcon from '$lib/icons/PersonAddIcon.svelte';

	let { data } = $props();
	let { organizationData, organizationMembers } = $derived(data);

	//* Manage
	let isInvitingUser = $state(false);
	let editingUser: OrgMemberRead | null = $state(null);
	let deletingUser: OrgMemberRead | null = $state(null);

	let isLoadingEdit = $state(false);
	let isLoadingDelete = $state(false);

	let selectedUserRole: (typeof userRoles)[number] = $state('GUEST');
	$effect(() => {
		selectedUserRole = editingUser?.role ?? 'GUEST';
	});
</script>

<svelte:head>
	<title>Team - Organization</title>
</svelte:head>

<section class="flex h-full flex-col gap-4 px-4 py-4 sm:px-8 sm:py-6">
	<div class="flex grow flex-col gap-4">
		<div class="flex items-center justify-between">
			<h2 class="text-sm font-medium text-[#667085]">ORGANIZATION MEMBERS</h2>

			<PermissionGuard reqOrgRole="ADMIN">
				<Button
					variant="outline"
					onclick={() => (isInvitingUser = true)}
					class="flex aspect-square items-center justify-center gap-2 px-0 py-0 xs:aspect-auto xs:px-6 xs:py-2"
				>
					<PersonAddIcon class="mb-0.5 h-5" />
					<span class="hidden xs:block">Invite people</span>
				</Button>
			</PermissionGuard>
		</div>

		<div class="mb-2 flex grow flex-col gap-1 overflow-auto">
			<div
				role="grid"
				style="grid-template-rows: min-content;"
				class="relative grid h-auto min-h-0 min-w-fit rounded-lg border border-[#F2F4F7] bg-white data-dark:bg-[#484C55]"
			>
				<div
					role="row"
					style="grid-template-columns: 45px minmax(8rem, 3fr) minmax(12rem, 2fr) minmax(6rem, 1fr) minmax(9rem, 1.5fr) 80px;"
					class="sticky top-0 z-20 grid h-[35px] px-2 text-xs font-medium text-[#98A2B3] sm:h-[50px] sm:text-sm"
				>
					<div role="columnheader" class="flex items-center px-2">No.</div>
					<div role="columnheader" class="flex items-center px-2">Name</div>
					<div role="columnheader" class="flex items-center px-2">Email</div>
					<div role="columnheader" class="flex items-center px-2">Role</div>
					<div role="columnheader" class="flex items-center px-2">Created at</div>
					<div role="columnheader" class="flex items-center px-2"></div>
				</div>
			</div>

			<div
				role="grid"
				style="grid-template-rows: repeat({organizationMembers.data?.length}, min-content);"
				class="relative grid h-1 min-h-0 min-w-fit grow overflow-y-auto overflow-x-visible rounded-lg border border-[#F2F4F7] bg-white data-dark:bg-[#484C55]"
			>
				{#each organizationMembers.data ?? [] as user, index}
					{@const userOrgCreatedAt = new Date(user.created_at).toLocaleString(undefined, {
						day: '2-digit',
						month: 'short',
						year: isThisYear(new Date(user.created_at)) ? undefined : 'numeric',
						hour: 'numeric',
						minute: '2-digit',
						second: '2-digit'
					})}
					<div
						role="row"
						style="grid-template-columns: 45px minmax(8rem, 3fr) minmax(12rem, 2fr) minmax(6rem, 1fr) minmax(9rem, 1.5fr) 80px;"
						class="group relative grid h-[45px] px-2 text-xs transition-colors duration-75 hover:bg-[#fafafa] data-dark:hover:bg-[#656970] sm:h-[60px] sm:text-sm [&>hr]:last:hidden"
					>
						<div role="gridcell" class="flex items-center px-2 pl-3">
							{index + 1}
						</div>
						<div role="gridcell" class="flex flex-col items-start justify-center px-2">
							<span
								title={user.user.name}
								class="line-clamp-1 break-all font-medium text-[#0C111D]"
							>
								{user.user.name}
							</span>
							<span title={user.user_id} class="line-clamp-1 break-all text-[#98A2B3]">
								{user.user_id}
							</span>
						</div>
						<div role="gridcell" class="flex items-center px-2">
							<span title={user.user.email ?? ''} class="line-clamp-1 break-all text-[#0C111D]">
								{user.user.email ?? ''}
							</span>
						</div>
						<div role="gridcell" class="flex items-center px-2">
							<span
								title={user.role}
								class="line-clamp-1 break-all font-medium capitalize text-[#0C111D]"
							>
								{lowerCase(user.role)}
							</span>
						</div>
						<div role="gridcell" class="flex items-center px-2 capitalize">
							<span title={userOrgCreatedAt} class="line-clamp-1 break-all">
								{userOrgCreatedAt}
							</span>
						</div>
						<div
							role="gridcell"
							class="flex items-center justify-center px-2 opacity-0 transition-opacity duration-75 group-hover:opacity-100 has-[:focus-visible]:opacity-100"
						>
							<Button
								variant="ghost"
								onclick={() => (editingUser = user)}
								title="Edit user"
								class="h-8 w-8 rounded-full p-0"
							>
								<EditIcon class="h-4" />
							</Button>

							<PermissionGuard reqOrgRole="ADMIN">
								<Button
									variant="ghost"
									onclick={() => (deletingUser = user)}
									title="Remove user"
									class="h-8 w-8 rounded-full p-0"
								>
									<DeleteIcon class="h-6" />
								</Button>
							</PermissionGuard>
						</div>

						<hr class="absolute bottom-0 left-0 right-0 border-[#F2F4F7]" />
					</div>
				{/each}
			</div>
		</div>
	</div>
</section>

<OrgInviteDialog bind:isInvitingUser />

<Dialog.Root bind:open={() => !!editingUser, () => (editingUser = null)}>
	<Dialog.Content class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Edit user role</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="editForm"
			use:enhance={() => {
				isLoadingEdit = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error updating user role', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else {
						editingUser = null;
					}

					isLoadingEdit = false;
					update({ reset: false });
				};
			}}
			method="POST"
			action="?/update"
			class="w-full grow overflow-auto"
		>
			<div class="h-full w-full grow overflow-auto py-3">
				<input type="hidden" value={editingUser?.user_id} name="user_id" />

				<div class="flex w-full flex-col gap-1 px-4 text-center sm:px-6">
					<Label required class="text-left text-sm font-medium text-black">User role*</Label>

					<input
						type="text"
						value={selectedUserRole}
						name="user_role"
						class="pointer-events-none invisible absolute"
					/>
					<Select.Root type="single" bind:value={selectedUserRole}>
						<Select.Trigger
							title="Select user role"
							class="flex h-10 min-w-full items-center justify-between gap-8 border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
						>
							{#snippet children()}
								<span class="line-clamp-1 whitespace-nowrap text-left font-normal capitalize">
									{selectedUserRole}
								</span>
							{/snippet}
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
					form="editForm"
					loading={isLoadingEdit}
					disabled={isLoadingEdit}
					class="relative grow px-6"
				>
					Save
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	bind:open={() => !!deletingUser,
	(v) => {
		if (!v) {
			deletingUser = null;
		}
	}}
>
	<Dialog.Content class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]">
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want to remove user
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{deletingUser?.user_id}`
				</span>?
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<form
				use:enhance={() => {
					isLoadingDelete = true;

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
							deletingUser = null;
						}

						isLoadingDelete = false;
						update({ reset: false });
					};
				}}
				method="POST"
				action="?/remove"
				class="flex gap-2 overflow-x-auto overflow-y-hidden"
			>
				<input
					type="text"
					name="user_id"
					value={deletingUser?.user_id}
					class="pointer-events-none invisible absolute"
				/>
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					variant="destructive"
					type="submit"
					loading={isLoadingDelete}
					disabled={isLoadingDelete}
					class="grow px-6"
				>
					Remove
				</Button>
			</form>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
