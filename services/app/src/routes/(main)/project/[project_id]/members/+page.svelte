<script lang="ts">
	import Fuse from 'fuse.js';
	import { MoreVertical, Search } from '@lucide/svelte';
	import { ROLE_COLORS } from '$lib/constants';
	import type { ProjectMemberRead } from '$lib/types';

	import {
		EditProjMemberDialog,
		ProjectInviteDialog,
		RemoveProjMemberDialog
	} from './(components)';
	import * as Table from '$lib/components/ui/table';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { formatDistanceToNow } from 'date-fns';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { data } = $props();

	let searchQuery = $state('');
	let isInvitingUser = $state(false);
	let isEditingUser = $state<ProjectMemberRead | null>(null);
	let isRemovingUser = $state<{
		open: boolean;
		value: NonNullable<Awaited<typeof data.projectMembers>['data']>[number] | null;
	}>({ open: false, value: null });

	const filterMembers = (members: NonNullable<Awaited<typeof data.projectMembers>['data']>) => {
		const fuse = new Fuse(members, {
			keys: ['user_id', 'user.name', 'user.email', 'role'],
			threshold: 0.4,
			includeScore: false
		});
		return searchQuery ? fuse.search(searchQuery).map((result) => result.item) : members;
	};
</script>

<svelte:head>
	<title>Project Members</title>
</svelte:head>

<div class="flex h-full flex-col pb-3">
	<div
		class="grid h-min flex-[0_0_auto] grid-cols-[minmax(0,auto)_min-content_min-content] items-center gap-1 overflow-auto px-7 pb-1.5 pt-1.5 [scrollbar-gutter:stable] sm:overflow-visible sm:pb-2 sm:pt-4"
	>
		<div class="relative">
			<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
				<Search size={16} class="text-gray-400" />
			</div>
			<Input
				type="text"
				bind:value={searchQuery}
				placeholder="Search members"
				class="h-8 w-64 rounded-lg bg-[#E4E7EC] py-2 pl-9 pr-4 sm:h-9"
			/>
		</div>

		<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
			<Button
				aria-label="Add user"
				onclick={() => (isInvitingUser = true)}
				class="relative flex aspect-square h-8 flex-[0_0_auto] items-center justify-center gap-1.5 px-2 py-2 text-xs xs:aspect-auto xs:h-9 xs:px-3 sm:text-sm"
			>
				<span class="xs:block">Add member</span>
			</Button>
		</PermissionGuard>
	</div>

	<div class="h-1 min-h-0 grow px-7">
		<div class="flex h-full flex-1 flex-col overflow-auto rounded-xl border bg-background">
			<Table.Root>
				<Table.Header class="sticky top-0 bg-[#F9FAFB]">
					<Table.Row class="uppercase">
						<Table.Head class="w-[200px]">Name</Table.Head>
						<Table.Head class="w-[150px]">Member</Table.Head>
						<Table.Head class="w-[150px]">Role</Table.Head>
						<Table.Head class="w-[50px]"></Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body class="overscroll-y-auto">
					{#await data.projectMembers}
						{#each Array(6) as _}
							<Table.Row>
								<Table.Cell colspan={100} class="p-1.5">
									<Skeleton class="h-[3.75rem] w-full" />
								</Table.Cell>
							</Table.Row>
						{/each}
					{:then projectMembers}
						{#if projectMembers.data}
							{@const filteredMembers = filterMembers(projectMembers.data)}
							{#if filteredMembers.length > 0}
								{#each filteredMembers as member}
									<Table.Row>
										<Table.Cell>
											<div class="flex items-center gap-3">
												<div
													class="h-10 w-10 flex-[0_0_auto] overflow-hidden rounded-full bg-gray-200"
												>
													<div
														class="flex h-full w-full items-center justify-center bg-primary/10 text-base font-medium text-primary"
													>
														{member.user.name?.charAt(0).toUpperCase() || '?'}
													</div>
												</div>
												<div>
													<div class="font-medium text-[#A62050]">{member.user.name}</div>
													<div class="text-sm text-muted-foreground">{member.user.email}</div>
												</div>
											</div>
										</Table.Cell>
										<Table.Cell class="w-1/2">
											{formatDistanceToNow(new Date(member.created_at), { addSuffix: true })}
										</Table.Cell>
										<Table.Cell>
											<span
												style:background={`${ROLE_COLORS[member.role]}32`}
												class="inline-flex items-center justify-center gap-x-1 rounded-lg bg-[#E26F64]/20 px-2 text-xs font-medium uppercase text-black"
											>
												<span
													style:color={`${ROLE_COLORS[member.role]}`}
													class="flex text-xl text-[#E26F64]">•</span
												>
												{member.role}</span
											>
										</Table.Cell>
										<Table.Cell>
											<DropdownMenu.Root>
												<DropdownMenu.Trigger
													class={buttonVariants({ variant: 'ghost', size: 'icon' }) + ' h-8 w-8'}
												>
													<MoreVertical class="h-4 w-4" />
												</DropdownMenu.Trigger>
												<DropdownMenu.Content align="end" class="w-fit min-w-40 space-y-1">
													<DropdownMenu.Item
														class="cursor-pointer"
														onclick={() => (isEditingUser = member)}
													>
														Edit role
													</DropdownMenu.Item>
													<DropdownMenu.Item
														class="text-destructive data-[highlighted]:text-destructive"
														onclick={() => (isRemovingUser = { open: true, value: member })}
													>
														Remove member
													</DropdownMenu.Item>
												</DropdownMenu.Content>
											</DropdownMenu.Root>
										</Table.Cell>
									</Table.Row>
								{/each}
							{:else}
								<div
									class="sticky left-1/2 flex h-64 -translate-x-1/2 items-center justify-center gap-2 text-center"
								>
									<div class="absolute flex w-80 flex-col">
										<span class="text-lg font-medium">No members found</span>
									</div>
								</div>
							{/if}
						{:else}
							<div
								class="sticky left-1/2 flex h-64 -translate-x-1/2 items-center justify-center gap-2 text-center"
							>
								<div class="absolute flex w-80 flex-col">
									<span class="text-lg font-medium">Error fetching members</span>
									<span class="text-sm">
										{projectMembers?.message.message || JSON.stringify(projectMembers?.message)}
									</span>
								</div>
							</div>
						{/if}
					{/await}
				</Table.Body>
			</Table.Root>
		</div>
	</div>
</div>

<ProjectInviteDialog
	bind:isInvitingUser
	organizationMembers={data.organizationMembers.data ?? []}
/>
<EditProjMemberDialog bind:isEditingUser />
<RemoveProjMemberDialog bind:isRemovingUser />
