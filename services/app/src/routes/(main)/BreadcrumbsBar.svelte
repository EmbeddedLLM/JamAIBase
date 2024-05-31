<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { page } from '$app/stores';
	import { invalidate } from '$app/navigation';
	import ChevronsUpDown from 'lucide-svelte/icons/chevrons-up-down';
	import { activeOrganization } from '$globalStore';
	import type { OrganizationReadRes } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	const { PUBLIC_IS_LOCAL } = env;

	let isSelectOrgOpen = false;

	let selectedTable: 'action-table' | 'knowledge-table' | 'chat-table' = 'action-table';
	$: if ($page.route.id?.endsWith('/project/[project_id]/action-table/[table_id]')) {
		selectedTable = 'action-table';
	} else if ($page.route.id?.endsWith('/project/[project_id]/knowledge-table/[table_id]')) {
		selectedTable = 'knowledge-table';
	} else if ($page.route.id?.endsWith('/project/[project_id]/chat-table/[table_id]')) {
		selectedTable = 'chat-table';
	} else {
		selectedTable = 'action-table';
	}

	$: activeProject = (
		($page.data.organizationData as OrganizationReadRes | undefined)?.projects ?? []
	).find((p) => p.id === $page.params.project_id);
</script>

<div class="flex items-center justify-between px-[18px] mt-4 mb-2 h-12 min-h-12">
	<div class="flex items-center gap-2 text-xs whitespace-nowrap overflow-auto">
		{#if PUBLIC_IS_LOCAL === 'false'}
			<DropdownMenu.Root>
				<DropdownMenu.Trigger asChild let:builder>
					<Button
						builders={[builder]}
						on:click={() => (isSelectOrgOpen = !isSelectOrgOpen)}
						class="flex items-center gap-1 pl-1.5 pr-[unset] py-1 h-[unset] w-[unset] text-xs text-black bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
					>
						<PeopleIcon class="h-3.5 mb-0.5" />
						<span>{$activeOrganization?.organization_name ?? 'Unknown'}</span>
						<ChevronsUpDown class="h-3.5" />
					</Button>
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" class="max-h-96 w-max overflow-y-auto">
					<DropdownMenu.Group>
						{#each $page.data.userData?.organizations ?? [] as org}
							<DropdownMenu.Item
								on:click={() => {
									$activeOrganization = org;
									invalidate('layout:root');
								}}
								class="flex justify-between gap-10 cursor-pointer {$activeOrganization?.organization_id ===
								org.organization_id
									? 'bg-[#F7F7F7]'
									: ''}"
							>
								{org.organization_name}
							</DropdownMenu.Item>
						{/each}
					</DropdownMenu.Group>
					<DropdownMenu.Separator />
					<DropdownMenu.Group>
						<DropdownMenu.Item asChild>
							<a
								href="/new-organization"
								class="flex items-center justify-start gap-1.5 pl-2 pr-16 py-1.5 text-sm hover:bg-accent rounded-md"
							>
								<AddIcon class="mb-0.5 h-2.5" />
								New Organization
							</a>
						</DropdownMenu.Item>
					</DropdownMenu.Group>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		{:else}
			<div class="flex items-center gap-1 px-1.5 py-1">
				<PeopleIcon class="h-3.5 mb-0.5" />
				<span> Default Organization </span>
			</div>
		{/if}
		<span class="text-[#999]">/</span>
		{#if PUBLIC_IS_LOCAL === 'false'}
			<a
				href="/project"
				class="flex items-center gap-1 px-1.5 py-1 hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
			>
				<AssignmentIcon class="h-3.5" />
				<span>Projects</span>
			</a>
		{:else}
			<div class="flex items-center gap-1 px-1.5 py-1">
				<AssignmentIcon class="h-3.5" />
				<span>Projects</span>
			</div>
		{/if}
		{#if $page.route.id?.startsWith('/(main)/project/[project_id]')}
			<span class="text-[#999]">/</span>
			<a
				href="/project/{PUBLIC_IS_LOCAL === 'false'
					? $page.params.project_id
					: 'default'}/{selectedTable}"
				class="flex items-center gap-1 px-1.5 py-1 hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
			>
				<AssignmentIcon class="h-3.5" />
				<span>
					{PUBLIC_IS_LOCAL === 'false' ? activeProject?.name ?? 'Unknown' : 'Default Project'}
				</span>
			</a>
		{/if}
		{#if $page.route.id?.endsWith('/project/[project_id]/action-table/[table_id]')}
			<span class="text-[#999]">/</span>
			<div class="flex items-center gap-1 px-1.5 py-1">
				<ActionTableIcon class="h-3.5" />
				<span>Action Table</span>
			</div>
		{:else if $page.route.id?.endsWith('/project/[project_id]/knowledge-table/[table_id]')}
			<span class="text-[#999]">/</span>
			<div class="flex items-center gap-1 px-1.5 py-1">
				<AssignmentIcon class="h-3.5" />
				<span>Knowledge Table</span>
			</div>
		{:else if $page.route.id?.endsWith('/project/[project_id]/chat-table/[table_id]')}
			<span class="text-[#999]">/</span>
			<div class="flex items-center gap-1 px-1.5 py-1">
				<ChatTableIcon class="h-3.5" />
				<span>Chat Table</span>
			</div>
		{/if}
	</div>
</div>
