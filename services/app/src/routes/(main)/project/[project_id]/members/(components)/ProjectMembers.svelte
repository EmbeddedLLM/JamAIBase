<script lang="ts">
	import Fuse from 'fuse.js';
	import { formatDistanceToNow } from 'date-fns';
	import { activeProject } from '$globalStore';
	import { ROLE_COLORS } from '$lib/constants';
	import type { ProjectMemberRead } from '$lib/types';
	import type { PageData } from '../$types';

	import { EditProjMemberDialog, RemoveProjMemberDialog, TransferProjOwnerDialog } from '.';
	import * as Tabs from '$lib/components/ui/tabs';
	import * as Table from '$lib/components/ui/table';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';

	let {
		user,
		projectMembers,
		isInvitingUser = $bindable()
	}: {
		user: PageData['user'];
		projectMembers: PageData['projectMembers'];
		isInvitingUser: boolean;
	} = $props();

	let searchQuery = $state('');
	let isEditingUser: ProjectMemberRead | null = $state(null);
	let isRemovingUser: { open: boolean; value: ProjectMemberRead | null } = $state({
		open: false,
		value: null
	});
	let isDeifyingUser: ProjectMemberRead | null = $state(null);

	const filterMembers = (members: NonNullable<Awaited<typeof projectMembers>['data']>) => {
		const fuse = new Fuse(members, {
			keys: ['user_id', 'user.name', 'user.email', 'role'],
			threshold: 0.4,
			includeScore: false
		});
		return searchQuery ? fuse.search(searchQuery).map((result) => result.item) : members;
	};
</script>

<Tabs.Content value="members" class="h-1 w-full grow flex-col gap-2 data-[state=active]:flex">
	<div class="flex items-center justify-between">
		<SearchBar
			bind:searchQuery
			isLoadingSearch={false}
			debouncedSearch={async () => {}}
			label="Search"
			placeholder="Search"
			class="w-[12rem]"
		/>

		<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
			<Button type="button" onclick={() => (isInvitingUser = true)} class="w-fit px-6">
				Invite member
			</Button>
		</PermissionGuard>
	</div>

	<div class="flex h-1 flex-1 grow flex-col overflow-auto rounded-xl border bg-background">
		<Table.Root>
			<Table.Header class="sticky top-0 bg-[#F9FAFB]">
				<Table.Row class="uppercase">
					<Table.Head class="w-[200px]">Name</Table.Head>
					<Table.Head class="w-[150px]">Member</Table.Head>
					<Table.Head class="w-[150px]">Role</Table.Head>
					<Table.Head class="w-[50px]">Actions</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body class="overscroll-y-auto">
				{#await projectMembers}
					{#each Array(6) as _}
						<Table.Row>
							<Table.Cell colspan={100} class="p-1.5">
								<Skeleton class="h-[3.75rem] w-full" />
							</Table.Cell>
						</Table.Row>
					{/each}
				{:then projectMembers}
					{#if projectMembers.data}
						{@const filteredProjMembers = filterMembers(projectMembers.data)}
						{#if filteredProjMembers.length > 0}
							{#each filteredProjMembers as projectMember}
								<Table.Row>
									<Table.Cell>
										<div class="flex items-center gap-2">
											<p
												title={projectMember.user.name}
												class="line-clamp-1 break-all text-[#A62050]"
											>
												{projectMember.user.name}
											</p>

											{#if $activeProject?.owner === projectMember.user_id}
												<span class="rounded-full bg-secondary px-1 py-0.5 text-xs text-white">
													Owner
												</span>
											{/if}
										</div>
										<span
											title={projectMember.user.email}
											class="line-clamp-1 break-all text-[#667085]"
										>
											{projectMember.user.email}
										</span>
									</Table.Cell>
									<Table.Cell class="w-1/2">
										{formatDistanceToNow(new Date(projectMember.created_at), { addSuffix: true })}
									</Table.Cell>
									<Table.Cell>
										<span
											style:background={`${ROLE_COLORS[projectMember.role]}32`}
											class="inline-flex items-center justify-center gap-x-1 rounded-lg bg-[#E26F64]/20 px-2 text-xs font-medium uppercase text-black"
										>
											<span
												style:color={`${ROLE_COLORS[projectMember.role]}`}
												class="flex text-xl text-[#E26F64]">•</span
											>
											{projectMember.role}</span
										>
									</Table.Cell>
									<Table.Cell class="min-w-[40px] max-w-[40px]">
										<DropdownMenu.Root>
											<DropdownMenu.Trigger>
												{#snippet child({ props })}
													<Button
														{...props}
														variant="ghost"
														onclick={(e) => e.preventDefault()}
														title="Manage user"
														class="aspect-square h-7 w-7 flex-[0_0_auto] p-0"
													>
														<MoreVertIcon class="h-[18px] w-[18px]" />
													</Button>
												{/snippet}
											</DropdownMenu.Trigger>
											<DropdownMenu.Content align="end">
												<DropdownMenu.Group>
													<DropdownMenu.Item
														onclick={() => (isEditingUser = projectMember)}
														class="text-[#344054] data-[highlighted]:text-[#344054]"
													>
														<span>Edit user</span>
													</DropdownMenu.Item>
													<PermissionGuard reqOrgRole="ADMIN">
														<DropdownMenu.Item
															onclick={() =>
																(isRemovingUser = { open: true, value: projectMember })}
															class="text-destructive data-[highlighted]:text-destructive"
														>
															<span>Remove user</span>
														</DropdownMenu.Item>
													</PermissionGuard>

													{#if $activeProject?.owner === user?.id && $activeProject?.owner !== projectMember.user_id}
														<DropdownMenu.Separator />
														<DropdownMenu.Item
															onclick={() => (isDeifyingUser = projectMember)}
															class="text-[#344054] data-[highlighted]:text-[#344054]"
														>
															<span>Make owner</span>
														</DropdownMenu.Item>
													{/if}
												</DropdownMenu.Group>
											</DropdownMenu.Content>
										</DropdownMenu.Root>
									</Table.Cell>
								</Table.Row>
							{/each}
						{:else}
							<Table.Row>
								<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
									<div class="absolute left-1/2 flex -translate-x-1/2 flex-col">
										<span class="text-lg font-medium">No project members found</span>
									</div>
								</Table.Cell>
							</Table.Row>
						{/if}
					{:else}
						<Table.Row>
							<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
								<div class="absolute left-1/2 flex w-[26rem] -translate-x-1/2 flex-col text-center">
									<span class="text-lg font-medium"> Error fetching project members </span>
									<span class="text-sm">
										{projectMembers?.message.message || JSON.stringify(projectMembers?.message)}
									</span>
								</div>
							</Table.Cell>
						</Table.Row>
					{/if}
				{/await}
			</Table.Body>
		</Table.Root>
	</div>
</Tabs.Content>

<EditProjMemberDialog bind:isEditingUser />
<RemoveProjMemberDialog bind:isRemovingUser />
<TransferProjOwnerDialog bind:isDeifyingUser />
