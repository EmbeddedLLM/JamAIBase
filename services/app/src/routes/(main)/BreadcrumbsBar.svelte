<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { tick } from 'svelte';
	import Bookmark from 'lucide-svelte/icons/bookmark';
	import Compass from 'lucide-svelte/icons/compass';
	import ChevronsUpDown from 'lucide-svelte/icons/chevrons-up-down';
	import { page } from '$app/stores';
	import { goto, invalidate } from '$app/navigation';
	import { activeOrganization, activeProject, loadingProjectData } from '$globalStore';

	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import HomeIcon from '$lib/icons/HomeIcon.svelte';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import KnowledgeTableIcon from '$lib/icons/KnowledgeTableIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import Check from 'lucide-svelte/icons/check';

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
</script>

<div
	class="flex items-center gap-2 px-2 sm:px-[18px] mt-3.5 sm:mt-4 mb-2 h-9 sm:h-12 min-h-9 sm:min-h-12 text-xs text-[#344054] whitespace-nowrap overflow-auto"
>
	{#if PUBLIC_IS_LOCAL === 'false'}
		<DropdownMenu.Root>
			<DropdownMenu.Trigger asChild let:builder>
				<Button
					builders={[builder]}
					variant="ghost"
					aria-label="Switch organizations"
					id="select-org-btn"
					on:click={() => (isSelectOrgOpen = !isSelectOrgOpen)}
					class="flex items-center gap-1 pl-1.5 pr-[unset] py-1 h-[unset] w-[unset] text-xs text-inherit rounded-sm"
				>
					<PeopleIcon class="h-3.5 mb-0.5" />
					<span>{$activeOrganization?.organization_name ?? 'Unknown'}</span>
					<ChevronsUpDown class="h-3.5" />
				</Button>
			</DropdownMenu.Trigger>
			<DropdownMenu.Content data-testid="org-selector" align="start" class="w-max overflow-y-auto">
				<DropdownMenu.Group class="max-h-48 overflow-auto">
					{#each $page.data.userData?.member_of ?? [] as org}
						<DropdownMenu.Item
							on:click={async () => {
								if (org?.organization_id !== $activeOrganization?.organization_id) {
									$activeOrganization = org;
									await tick();
									if ($page.route.id?.includes('/project/[project_id]')) {
										goto('/project');
									} else {
										invalidate('layout:root');
									}
								}
							}}
							class="flex items-center gap-1 text-xs cursor-pointer {$activeOrganization?.organization_id ===
							org.organization_id
								? 'bg-[#F7F7F7]'
								: ''} rounded-sm"
						>
							<PeopleIcon class="h-3.5 mb-0.5" />
							{org.organization_name}

							<Check
								class="h-3.5 ml-auto"
								style="display: {$activeOrganization?.organization_id === org.organization_id
									? 'block'
									: 'none'}"
							/>
						</DropdownMenu.Item>
					{/each}
				</DropdownMenu.Group>
				<DropdownMenu.Separator />
				<DropdownMenu.Group>
					<DropdownMenu.Item asChild>
						<a
							href="/new-organization"
							class="flex items-center justify-start gap-1.5 pl-2 pr-16 py-1.5 text-xs hover:bg-accent rounded-sm"
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
	<span class="text-[#D0D5DD]">/</span>
	{#if $page.route.id?.startsWith('/(main)/project')}
		<a
			href="/project"
			class="flex items-center gap-1.5 px-1.5 py-1 hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
		>
			<AssignmentIcon class="h-3" />
			<span>Projects</span>
		</a>
	{:else if $page.url.pathname.startsWith('/organization')}
		<div class="flex items-center gap-1.5 px-1.5 py-1">
			<PeopleIcon class="h-3.5 mb-0.5" />
			<span>Organization</span>
		</div>
	{:else if $page.url.pathname.startsWith('/home')}
		<div class="flex items-center gap-1.5 px-1.5 py-1">
			<HomeIcon class="h-3.5 w-3.5 mb-0.5" />
			<span>Home</span>
		</div>
	{:else if $page.route.id?.endsWith('/template')}
		<div class="flex items-center gap-1.5 px-1.5 py-1">
			<Compass class="h-3.5 w-3.5" />
			<span>Discover</span>
		</div>
	{:else if $page.route.id?.startsWith('/(main)/template/[template_id]')}
		<a
			href="/template/{$page.params.template_id}"
			class="flex items-center gap-1.5 px-1.5 py-1 hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
		>
			<span class="bg-[#F7E7E8] rounded-[3px] p-0.5">
				<Bookmark class="flex-[0_0_auto] h-3 w-3 text-[#E55959]" />
			</span>
			<span>{$page.data?.templateData?.data?.name ?? $page.params.template_id}</span>
		</a>
	{/if}

	{#if $page.route.id?.startsWith('/(main)/project/[project_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<a
			href="/project/{$page.params.project_id}/{selectedTable}"
			class="flex items-center gap-1.5 px-1.5 py-1 hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1] rounded-sm transition-colors"
		>
			<AssignmentIcon class="h-3" />
			<span>
				{$activeProject?.name ??
					($loadingProjectData.loading ? 'Loading...' : $page.params.project_id)}
			</span>
		</a>
	{/if}

	{#if $page.route.id?.endsWith('/action-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<ActionTableIcon class="h-3.5" />
			<span>{$page.params.table_id}</span>
		</div>
	{:else if $page.route.id?.endsWith('/knowledge-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<KnowledgeTableIcon class="h-[18px]" />
			<span>{$page.params.table_id}</span>
		</div>
	{:else if $page.route.id?.endsWith('/chat-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<ChatTableIcon class="h-3.5" />
			<span>{$page.params.table_id}</span>
		</div>
	{/if}
</div>

<style>
	::-webkit-scrollbar {
		height: 3px;
	}
</style>
