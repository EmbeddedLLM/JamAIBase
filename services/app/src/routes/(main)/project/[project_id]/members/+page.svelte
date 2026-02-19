<script lang="ts">
	import Fuse from 'fuse.js';
	import { MoreVertical, Search } from '@lucide/svelte';
	import { activeProject } from '$globalStore';
	import { ROLE_COLORS } from '$lib/constants';
	import type { ProjectMemberRead } from '$lib/types';

	import { ProjectInvitations, ProjectInviteDialog, ProjectMembers } from './(components)';
	import * as Table from '$lib/components/ui/table';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { formatDistanceToNow } from 'date-fns';
	import * as Tabs from '$lib/components/ui/tabs';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { data } = $props();

	let searchQuery = $state('');
	let isInvitingUser = $state(false);

	let projInvitationComponent = $state<ProjectInvitations | undefined>();
</script>

<svelte:head>
	<title>Project Members</title>
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
			<!-- <PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
				<Tabs.Trigger
					value="invitations"
					class="rounded-lg border border-transparent data-[state=active]:border-[#FFD8DF] data-[state=active]:bg-[#FFEFF2] data-[state=active]:text-[#950048] data-[state=active]:shadow-[unset]"
				>
					Invitations
				</Tabs.Trigger>
			</PermissionGuard> -->
		</Tabs.List>

		<ProjectMembers bind:isInvitingUser user={data.user} projectMembers={data.projectMembers} />

		<!-- <PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
			<ProjectInvitations bind:this={projInvitationComponent} bind:isInvitingUser />
		</PermissionGuard> -->
	</Tabs.Root>
</div>

<ProjectInviteDialog
	bind:isInvitingUser
	organizationMembers={data.organizationMembers.data ?? []}
/>
