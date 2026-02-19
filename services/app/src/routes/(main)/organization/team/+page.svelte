<script lang="ts">
	import { OrgInvitations, OrgInviteDialog, OrgMembers } from './(components)';
	import * as Tabs from '$lib/components/ui/tabs';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { data } = $props();

	let orgInvitationComponent = $state<OrgInvitations | undefined>();

	let isInvitingUser = $state(false);
</script>

<svelte:head>
	<title>Team - Organization</title>
</svelte:head>

<div class="grow px-4 py-3">
	<Tabs.Root value="members" class="flex h-full flex-col items-start rounded-lg bg-white p-2">
		<Tabs.List class="h-[unset] gap-0.5 bg-[unset] p-0">
			<Tabs.Trigger
				value="members"
				class="rounded-lg border border-transparent data-[state=active]:border-[#FFD8DF] data-[state=active]:bg-[#FFEFF2] data-[state=active]:text-[#950048] data-[state=active]:shadow-[unset]"
			>
				Members
			</Tabs.Trigger>
			<PermissionGuard reqOrgRole="ADMIN">
				<Tabs.Trigger
					value="invitations"
					class="rounded-lg border border-transparent data-[state=active]:border-[#FFD8DF] data-[state=active]:bg-[#FFEFF2] data-[state=active]:text-[#950048] data-[state=active]:shadow-[unset]"
				>
					Invitations
				</Tabs.Trigger>
			</PermissionGuard>
		</Tabs.List>

		<OrgMembers
			bind:isInvitingUser
			user={data.user}
			organizationData={data.organizationData}
			organizationMembers={data.organizationMembers}
		/>

		<PermissionGuard reqOrgRole="ADMIN">
			<OrgInvitations bind:this={orgInvitationComponent} bind:isInvitingUser />
		</PermissionGuard>
	</Tabs.Root>
</div>

<OrgInviteDialog
	refetchOrgInvites={orgInvitationComponent?.refetchOrgInvites}
	bind:isInvitingUser
/>
