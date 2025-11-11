<script lang="ts">
	import { signOut } from '@auth/sveltekit/client';
	import { FolderPlus, Plus, Settings } from '@lucide/svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { cn } from '$lib/utils';

	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import LogoutIcon from '$lib/icons/LogoutIcon.svelte';

	let { class: className = undefined }: { class?: string } = $props();

	let open = $state(false);
</script>

<DropdownMenu.Root bind:open>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<button
				{...props}
				onclick={(e) => e.stopPropagation()}
				title="User details"
				class={cn(
					'z-[10] hidden max-h-[2.5rem] w-44 items-center gap-2 rounded-full border bg-white p-1 pr-2 transition-colors md:flex',
					page.data.hideBreadcrumbs ? 'absolute right-6 top-[19px]' : 'mr-6 mt-1.5',
					open ? 'border-[#FFB6C3] bg-[#FFEFF2]' : 'border-transparent',
					className
				)}
			>
				<div
					class="flex aspect-square h-8 w-8 flex-[0_0_auto] items-center justify-center overflow-hidden rounded-full bg-[#E8F0F3] outline-2 transition-transform"
				>
					{#if page.data.user?.picture_url}
						<img
							src={page.data.user?.picture_url}
							alt="User Avatar"
							class="h-full w-full object-cover"
						/>
					{:else}
						<span class="text-md uppercase text-[#1B7288]">
							{(page.data.user?.name ?? 'Default User').charAt(0)}
						</span>
					{/if}
				</div>

				<p class="line-clamp-1 text-sm text-[#344054]">
					{page.data.user?.name ?? 'Unknown'}
				</p>
			</button>
		{/snippet}
	</DropdownMenu.Trigger>

	<DropdownMenu.Content
		data-testid="column-actions-dropdown"
		alignOffset={-65}
		class="w-44 text-[#344054]"
	>
		<div class="cursor-default break-all px-1.5 pb-3 pt-1 text-sm text-[#667085]">
			{page.data.user?.email}
		</div>

		<DropdownMenu.Group>
			<DropdownMenu.Item>
				{#snippet child({ props })}
					<a {...props} href="/join-organization">
						{@render joinOrgIcon('h-4 w-4')}
						<span>Join organization</span>
					</a>
				{/snippet}
			</DropdownMenu.Item>
			<DropdownMenu.Item>
				{#snippet child({ props })}
					<a {...props} href="/join-project">
						<FolderPlus />
						<span>Join project</span>
					</a>
				{/snippet}
			</DropdownMenu.Item>
			<DropdownMenu.Item>
				{#snippet child({ props })}
					<a {...props} href="/new-organization">
						<Plus />
						<span>Create organization</span>
					</a>
				{/snippet}
			</DropdownMenu.Item>
			<DropdownMenu.Item>
				{#snippet child({ props })}
					<a
						{...props}
						href="/project?new"
						data-sveltekit-reload={page.url.pathname === '/project'}
					>
						<Plus />
						<span>Create project</span>
					</a>
				{/snippet}
			</DropdownMenu.Item>
		</DropdownMenu.Group>

		<DropdownMenu.Separator class="bg-[#E4E7EC]" />

		<DropdownMenu.Group>
			<DropdownMenu.Item>
				{#snippet child({ props })}
					<a {...props} href="/settings/account">
						<Settings />
						<span>Account Settings</span>
					</a>
				{/snippet}
			</DropdownMenu.Item>
			<DropdownMenu.Item
				onclick={page.data.auth0Mode ? () => goto('/logout') : () => signOut()}
				class="!text-[#F04438]"
			>
				<LogoutIcon class="h-4 w-4 [&_path]:stroke-[1.2]" />
				<span>Sign out</span>
			</DropdownMenu.Item>
		</DropdownMenu.Group>
	</DropdownMenu.Content>
</DropdownMenu.Root>

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
