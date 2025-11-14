<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import {
		ArrowLeftRight,
		Bookmark,
		ChartLine,
		Check,
		ChevronDown,
		Clipboard,
		Compass,
		LayoutDashboard,
		MessageCircle,
		Plus
	} from '@lucide/svelte';
	import { page } from '$app/state';
	import { goto, invalidate } from '$app/navigation';
	import { activeOrganization, activeProject, loadingProjectData } from '$globalStore';
	import type { User } from '$lib/types';

	import { m } from '$lib/paraglide/messages';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import HomeIcon from '$lib/icons/HomeIcon.svelte';
	import ActionTableIcon from '$lib/icons/ActionTableIcon.svelte';
	import KnowledgeTableIcon from '$lib/icons/KnowledgeTableIcon.svelte';
	import ChatTableIcon from '$lib/icons/ChatTableIcon.svelte';

	const { PUBLIC_ADMIN_ORGANIZATION_ID } = publicEnv;

	let isInSystemPages = $derived(page.url.pathname.startsWith('/system'));

	let selectedTable: 'action-table' | 'knowledge-table' | 'chat-table' = $derived.by(() => {
		if (page.route.id?.endsWith('/project/[project_id]/action-table/[table_id]')) {
			return 'action-table';
		} else if (page.route.id?.endsWith('/project/[project_id]/knowledge-table/[table_id]')) {
			return 'knowledge-table';
		} else if (page.route.id?.endsWith('/project/[project_id]/chat-table/[table_id]')) {
			return 'chat-table';
		} else {
			return 'action-table';
		}
	});
</script>

<div
	class="mb-2 mt-3.5 flex h-9 min-h-9 items-center gap-2 overflow-auto whitespace-nowrap px-2 text-xs text-[#667085] sm:mt-4 sm:h-12 sm:min-h-12 sm:px-[18px] md:text-sm"
>
	{#if page.url.pathname.startsWith('/system')}
		<div
			class="flex items-center gap-1.5 rounded-lg bg-[#2DC6D1]/10 px-2 py-1.5 text-xs text-[#17787E] md:text-sm"
		>
			<LayoutDashboard class="h-3.5 w-3.5" />
			<span>System</span>
		</div>
	{:else if page.url.pathname.startsWith('/chat')}
		<div
			class="flex items-center gap-1.5 rounded-lg bg-[#FFB6C3]/20 px-2 py-1.5 text-xs text-[#950048] md:text-sm"
		>
			<MessageCircle class="h-[13px] w-[13px]" />
			<span>JamAI Chat</span>
		</div>
	{:else}
		<DropdownMenu.Root>
			<DropdownMenu.Trigger id="select-org-btn" aria-label={m['breadcrumbs.org_btn']()}>
				{#snippet child({ props })}
					<Button
						{...props}
						variant="ghost"
						class="flex h-[unset] w-[unset] items-center gap-1.5 rounded-lg bg-[#FFB6C3]/20 py-1.5 pl-2 pr-0.5 text-xs font-normal !text-[#950048] text-inherit hover:bg-[#FFB6C3]/40 focus-visible:bg-[#FFB6C3]/40 active:bg-[#FFB6C3]/40 md:text-sm"
					>
						<PeopleIcon class="mb-0.5 h-[15px] w-[15px]" />
						<span>{$activeOrganization?.name ?? m['breadcrumbs.org_placeholder']()}</span>
						<ChevronDown class="h-3.5" />
					</Button>
				{/snippet}
			</DropdownMenu.Trigger>
			<DropdownMenu.Content data-testid="org-selector" align="start" class="w-max overflow-y-auto">
				<DropdownMenu.Group class="max-h-48 overflow-auto">
					<p class="mb-1.5 ml-1.5 mt-1 text-xs font-medium uppercase text-[#999]">Organization</p>

					{#each (page.data.user as User)?.org_memberships ?? [] as orgMembership}
						{@const org = (page.data.user as User)?.organizations.find(
							(org) => org.id === orgMembership.organization_id
						)}
						{#if org}
							<DropdownMenu.Item
								onclick={async () => {
									if (org?.id !== $activeOrganization?.id) {
										activeOrganization.setOrgCookie(org.id);
										if (page.route.id?.includes('/project/[project_id]')) {
											goto('/project');
										} else {
											invalidate('layout:root');
										}
									}
								}}
								class="flex cursor-pointer items-center gap-1 text-xs {$activeOrganization?.id ===
								org.id
									? '!bg-[#D0F7FB]'
									: ''} rounded-sm"
							>
								<PeopleIcon class="mb-0.5 h-3.5" />
								{org.name}

								<Check
									class="ml-auto h-3.5"
									style="display: {$activeOrganization?.id === org.id ? 'block' : 'none'}"
								/>
							</DropdownMenu.Item>
						{/if}
					{/each}
				</DropdownMenu.Group>
				<DropdownMenu.Separator />
				<DropdownMenu.Group>
					<DropdownMenu.Item>
						{#snippet child({ props })}
							<a
								{...props}
								href="/join-organization"
								class="flex items-center justify-start gap-1.5 rounded-sm py-1.5 pl-2 pr-16 text-xs hover:bg-accent"
							>
								{@render joinOrgIcon('h-4 w-4')}
								{m['breadcrumbs.org_join_btn']()}
							</a>
						{/snippet}
					</DropdownMenu.Item>
					<DropdownMenu.Item>
						{#snippet child({ props })}
							<a
								{...props}
								href="/new-organization"
								class="flex items-center justify-start gap-1.5 rounded-sm py-1.5 pl-2 pr-16 text-xs hover:bg-accent"
							>
								<Plus class="h-4 w-4" />
								{m['breadcrumbs.org_create_btn']()}
							</a>
						{/snippet}
					</DropdownMenu.Item>
				</DropdownMenu.Group>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
	{/if}

	{#if !page.url.pathname.startsWith('/chat') && $activeOrganization?.id === PUBLIC_ADMIN_ORGANIZATION_ID}
		<Button
			tvTheme={!isInSystemPages}
			variant="outline"
			href={isInSystemPages ? '/' : '/system'}
			class="h-[unset] gap-1 rounded-lg bg-white px-2 py-[5px] text-xs md:text-sm {!isInSystemPages &&
				'border-[#0AB9C4] text-[#019AA3] hover:bg-[#D1F7F9]'}"
		>
			<ArrowLeftRight class="mx-0.5 h-[13px] w-[13px]" />
			Switch to {isInSystemPages ? 'Organization' : 'System'}
		</Button>
	{/if}

	{#if page.route.id?.startsWith('/(main)/project')}
		<a
			href="/project"
			class="flex items-center gap-1.5 rounded-sm px-1.5 py-1 transition-colors hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1]"
		>
			<Clipboard class="h-[14px] w-[14px]" />
			<span>{m['project.heading']()}</span>
		</a>
	{:else if page.url.pathname.startsWith('/organization')}
		<div class="flex items-center gap-1.5 px-1.5 py-1">
			<PeopleIcon class="mb-0.5 h-3.5" />
			<span>Organization</span>
		</div>
	{:else if page.url.pathname.startsWith('/analytics')}
		<div class="flex items-center gap-1.5 px-1.5 py-1">
			<ChartLine class="mb-0.5 h-3.5 w-3.5" />
			<span>Analytics</span>
		</div>
	{:else if page.url.pathname.startsWith('/template')}
		<a
			href="/template"
			class="flex items-center gap-1.5 rounded-sm px-1.5 py-1 transition-colors hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1]"
		>
			<Compass class="h-3.5 w-3.5" />
			<span>Discover</span>
		</a>
	{/if}

	{#if page.route.id?.startsWith('/(main)/(cloud)/template/[template_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<a
			href="/template/{page.params.template_id}"
			class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#F2F4F7] hover:text-[#344054] data-dark:hover:bg-white/[0.1]"
		>
			<span class="rounded-[3px] bg-[#F7E7E8] p-0.5">
				<Bookmark class="h-3 w-3 flex-[0_0_auto] text-[#E55959]" />
			</span>
			<span>{page.data?.templateData?.data?.name ?? page.params.template_id}</span>
		</a>
	{:else if page.route.id?.startsWith('/(main)/project/[project_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<a
			href="/project/{page.params.project_id}/{selectedTable}"
			class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#F2F4F7] hover:text-[#344054] data-dark:hover:bg-white/[0.1]"
		>
			<Clipboard class="h-[14px] w-[14px]" />
			<span>
				{$activeProject?.name ??
					($loadingProjectData.loading ? 'Loading...' : page.params.project_id)}
			</span>
		</a>
	{:else if page.route.id?.startsWith('/(main)/template/[template_id]')}
		<a
			href="/template/{page.params.template_id}"
			class="flex items-center gap-1.5 rounded-sm px-1.5 py-1 transition-colors hover:bg-[#F2F4F7] hover:text-accent-foreground data-dark:hover:bg-white/[0.1]"
		>
			<span class="rounded-[3px] bg-[#F7E7E8] p-0.5">
				<Bookmark class="h-3 w-3 flex-[0_0_auto] text-[#E55959]" />
			</span>
			<span>{page.data?.templateData?.data?.name ?? page.params.template_id}</span>
		</a>
	{/if}

	{#if page.route.id?.endsWith('/action-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<ActionTableIcon class="h-3.5" />
			<span>{page.params.table_id}</span>
		</div>
	{:else if page.route.id?.endsWith('/knowledge-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<KnowledgeTableIcon class="h-[18px]" />
			<span>{page.params.table_id}</span>
		</div>
	{:else if page.route.id?.endsWith('/chat-table/[table_id]')}
		<span class="text-[#D0D5DD]">/</span>
		<div class="flex items-center gap-1 px-1.5 pl-0.5 pr-1">
			<ChatTableIcon class="h-3.5" />
			<span>{page.params.table_id}</span>
		</div>
	{/if}
</div>

{#snippet joinOrgIcon(className = '')}
	<svg viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" class={className}>
		<path
			d="M10.1737 7.92361C9.35291 7.92361 8.6875 7.2582 8.6875 6.43739C8.6875 5.61657 9.35291 4.95117 10.1737 4.95117C10.9945 4.95117 11.6599 5.61657 11.6599 6.43739C11.6599 7.2582 10.9945 7.92361 10.1737 7.92361Z"
			stroke="#344054"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.01562 10.2167C8.22035 10.0003 8.45726 9.81508 8.71904 9.668C9.1636 9.41828 9.66492 9.28711 10.1748 9.28711C10.6847 9.28711 11.1861 9.41828 11.6306 9.668C11.8229 9.77604 12.0018 9.90462 12.1643 10.0511"
			stroke="#344054"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M5.36514 7.4461C4.348 7.4461 3.52344 6.62154 3.52344 5.6044C3.52344 4.58725 4.348 3.7627 5.36514 3.7627C6.38229 3.7627 7.20685 4.58725 7.20685 5.6044C7.20685 6.62154 6.38229 7.4461 5.36514 7.4461Z"
			stroke="#344054"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.81738 12.7052C8.72552 11.6051 8.45141 10.8818 8.30113 10.6271C7.98117 10.0832 7.53149 9.63354 6.99531 9.32156C6.45914 9.00957 5.8545 8.8457 5.23952 8.8457C4.62454 8.8457 4.0199 9.00957 3.48373 9.32156C3.05559 9.57068 2.68261 9.90752 2.38677 10.3102L2.19922 10.5909"
			stroke="#344054"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M7 13C3.68629 13 1 10.3138 1 7C1 3.68629 3.68629 1 7 1C10.3138 1 13 3.68629 13 7C13 10.3138 10.3138 13 7 13Z"
			stroke="#344054"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/snippet}

<style>
	::-webkit-scrollbar {
		height: 3px;
	}
</style>
