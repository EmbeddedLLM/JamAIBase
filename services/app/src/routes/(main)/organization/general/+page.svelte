<script lang="ts">
	import { enhance } from '$app/forms';
	import { activeOrganization } from '$globalStore';

	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import InputText from '$lib/components/InputText.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import WarningIcon from '$lib/icons/WarningIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import CopyIcon from '$lib/icons/CopyIcon.svelte';
	import CheckDoneIcon from '$lib/icons/CheckDoneIcon.svelte';

	let isEditingOrgName = $state(false);
	let editOrgName = $state($activeOrganization?.name ?? '');
	let isLoadingEditOrgName = $state(false);

	let isLeavingOrg = $state(false);
	let isLoadingLeaveOrg = $state(false);

	let confirmOrgName = $state('');
	let isDeletingOrg = $state(false);
	let isLoadingDeleteOrg = $state(false);

	let orgIdCopied = $state(false);
	let orgIdCopiedTimeout: ReturnType<typeof setTimeout> | undefined = $state();
</script>

<svelte:head>
	<title>General - Organization</title>
</svelte:head>

<section class="flex h-full flex-col gap-4 overflow-auto px-4 py-4 sm:px-8 sm:py-6">
	<h2 class="text-sm font-medium text-[#667085]">YOUR ORGANIZATION</h2>

	<div class="mb-8 flex h-min w-[clamp(0px,100%,600px)] flex-col gap-4 rounded-lg bg-white p-4">
		<div class="flex items-center justify-between">
			<div class="flex flex-col gap-1">
				<p class="text-xs font-medium uppercase text-[#98A2B3]">Organization Name</p>
				<span class="text-sm">{$activeOrganization?.name ?? ''}</span>
			</div>

			<PermissionGuard reqOrgRole="ADMIN">
				<Button
					variant="outline"
					onclick={() => {
						editOrgName = $activeOrganization?.name ?? '';
						isEditingOrgName = true;
					}}
					title="Edit organization name"
					class="px-6"
				>
					Edit
				</Button>
			</PermissionGuard>
		</div>

		<div class="flex flex-col gap-1">
			<p class="text-xs font-medium uppercase text-[#98A2B3]">Organization ID</p>
			<div class="flex items-center gap-1">
				<span class="text-sm">{$activeOrganization?.id ?? ''}</span>
				<Button
					variant="ghost"
					aria-label="Copy organization ID"
					onclick={() => {
						navigator.clipboard.writeText($activeOrganization?.id ?? '');
						clearTimeout(orgIdCopiedTimeout);
						orgIdCopied = true;
						orgIdCopiedTimeout = setTimeout(() => (orgIdCopied = false), 1500);
					}}
					class="group relative aspect-square h-[unset] rounded-full p-[1px]"
				>
					<CopyIcon class="h-5 text-[#98A2B3]" />

					<Tooltip
						arrowSize={8}
						class="{orgIdCopied
							? 'absolute bg-[#12B76A] after:!border-t-[#12B76A]'
							: '-left-2'} -top-7 opacity-0 transition-opacity group-hover:opacity-100"
					>
						{#if orgIdCopied}
							<div class="flex gap-1">
								<CheckDoneIcon class="h-4 w-4" />
								Copied to clipboard
							</div>
						{:else}
							Copy
						{/if}
					</Tooltip>
				</Button>
			</div>
		</div>
	</div>

	<div class="mt-auto flex flex-col gap-2">
		<h2 class="text-sm font-medium text-[#667085]">ORGANIZATION REMOVAL</h2>

		<p class="mb-1 text-[0] text-[#667085] [&>span]:text-[13px]">
			<span>Leaving this organization will remove you from it</span>
			<span>
				<PermissionGuard reqOrgRole="ADMIN">
					, while deleting it will permanently remove all data associated with it.
					{#snippet deniedMessage()}
						.
					{/snippet}
				</PermissionGuard>
			</span>
		</p>

		<div class="flex w-[clamp(0px,100%,600px)] flex-col gap-2 sm:flex-row sm:items-center">
			<Button onclick={() => (isLeavingOrg = true)} class="px-8">Leave Organization</Button>

			<PermissionGuard reqOrgRole="ADMIN">
				<Button onclick={() => (isDeletingOrg = true)} variant="outline" class="px-8">
					Delete Organization
				</Button>
			</PermissionGuard>
		</div>
	</div>
</section>

<Dialog.Root
	bind:open={isEditingOrgName}
	onOpenChange={() => (editOrgName = $activeOrganization?.name ?? '')}
>
	<Dialog.Content data-testid="edit-org-name-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Edit organization name</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="editOrgNameForm"
			use:enhance={() => {
				isLoadingEditOrgName = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error updating organization details', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					}

					await update({ reset: false });
					isLoadingEditOrgName = false;
					isEditingOrgName = false;
				};
			}}
			method="POST"
			action="?/update"
			class="w-full grow overflow-auto"
		>
			<div class="flex h-full w-full flex-col space-y-1 px-4 py-3 sm:px-6">
				<Label required for="organization_name" class="text-xs sm:text-sm">Organization name</Label>

				<InputText
					bind:value={editOrgName}
					id="organization_name"
					name="organization_name"
					placeholder="Required"
				/>
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
					form="editOrgNameForm"
					loading={isLoadingEditOrgName}
					disabled={isLoadingEditOrgName || editOrgName === $activeOrganization?.name}
					class="relative grow px-6"
				>
					Save
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={isLeavingOrg}>
	<Dialog.Content class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]">
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="leavingOrgForm"
			use:enhance={() => {
				isLoadingLeaveOrg = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error leaving organization', {
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

					isLoadingLeaveOrg = false;
					update({ reset: false, invalidateAll: false });
				};
			}}
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			method="POST"
			action="?/leave"
			class="flex flex-col items-start gap-2 p-8 pb-10"
		>
			<WarningIcon class="mb-1 h-10 text-warning" />
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want to leave organization
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{$activeOrganization?.name}`
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
					form="leavingOrgForm"
					loading={isLoadingLeaveOrg}
					disabled={isLoadingLeaveOrg}
					class="grow px-6"
				>
					Leave
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	bind:open={isDeletingOrg}
	onOpenChange={(e) => {
		if (!e) {
			confirmOrgName = '';
		}
	}}
>
	<Dialog.Content
		data-testid="confirm-delete-org-dialog"
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Delete organization</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="deleteOrgForm"
			use:enhance={() => {
				isLoadingDeleteOrg = true;

				return async ({ result, update }) => {
					if (result.type !== 'success') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error deleting organization', {
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

					isLoadingDeleteOrg = false;
					update({ reset: false, invalidateAll: false });
				};
			}}
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			method="POST"
			action="?/delete"
			class="w-full grow overflow-auto"
		>
			<div class="flex h-full w-full grow flex-col gap-4 py-3">
				<p class="px-4 text-sm text-text/60 sm:px-6">
					Do you really want to delete organization
					<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
						`{$activeOrganization?.name}`
					</span>? This process cannot be undone.
				</p>

				<div class="flex w-full flex-col space-y-1 px-4 sm:px-6">
					<Label for="organization_name" class="text-sm text-black">
						Enter organization name to confirm
					</Label>

					<InputText
						bind:value={confirmOrgName}
						id="organization_name"
						name="organization_name"
						placeholder="Organization name"
					/>
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
					form="deleteOrgForm"
					loading={isLoadingDeleteOrg}
					disabled={isLoadingDeleteOrg || confirmOrgName !== $activeOrganization?.name}
					class="relative grow px-6"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
