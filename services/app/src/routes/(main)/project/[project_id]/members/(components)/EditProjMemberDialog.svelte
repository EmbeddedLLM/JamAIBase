<script lang="ts">
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import { activeProject } from '$globalStore';
	import { userRoles } from '$lib/constants';
	import type { ProjectMemberRead } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	let { isEditingUser = $bindable() }: { isEditingUser: ProjectMemberRead | null } = $props();

	let isLoadingEdit = $state(false);

	let selectedUserRole: (typeof userRoles)[number] = $state('GUEST');
	$effect(() => {
		selectedUserRole = isEditingUser?.role ?? 'GUEST';
	});
</script>

<Dialog.Root bind:open={() => !!isEditingUser, () => (isEditingUser = null)}>
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
						isEditingUser = null;
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
				<input type="hidden" value={$activeProject?.id} name="project_id" />
				<input type="hidden" value={isEditingUser?.user_id} name="user_id" />

				<div class="flex w-full flex-col gap-1 px-4 text-center sm:px-6">
					<Label required class="text-left text-sm font-medium text-black">User role</Label>

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
