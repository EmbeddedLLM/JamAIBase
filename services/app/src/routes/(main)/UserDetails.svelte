<script lang="ts">
	import { page } from '$app/state';
	import { activeOrganization, showDock } from '$globalStore';
	import { cn } from '$lib/utils';
	import type { User } from '$lib/types';

	let settingsBtnHasFocus = false;
</script>

<a
	href="/settings"
	class={cn(
		'flex flex-col gap-2 px-3 py-3 transition-[padding,background] duration-300 hover:bg-accent md:hidden',
		$showDock ? 'translate-x-[0.5px] rounded-b-2xl sm:px-4 sm:py-3' : 'rounded-b-full sm:p-3'
	)}
>
	<div
		class="relative flex items-center {$showDock
			? 'gap-4'
			: 'gap-0'} w-full rounded-lg text-left transition-[gap] duration-300"
	>
		<div class="placeholder pointer-events-none relative select-none rounded-full">
			<div
				class="flex h-9 w-9 items-center justify-center rounded-full bg-[#E8F0F3] {settingsBtnHasFocus &&
				!$showDock
					? 'outline'
					: '-translate-x-0.5 outline-none'} aspect-square overflow-hidden outline-2 transition-transform"
			>
				{#if (page.data.user as User)?.picture_url}
					<img
						src={(page.data.user as User).picture_url}
						alt="User Avatar"
						class="h-full w-full object-cover"
					/>
				{:else}
					<span class="text-xl uppercase text-[#1B7288]">
						{((page.data.user as User)?.name ?? 'Default User').charAt(0)}
					</span>
				{/if}
			</div>
		</div>

		<div
			class="flex w-auto grow flex-col {$showDock
				? 'sm:w-full sm:opacity-100'
				: 'sm:pointer-events-none sm:w-0 sm:opacity-0'} transition-[opacity,_width] duration-300"
		>
			<span class="line-clamp-1 break-all">
				{(page.data.user as User)?.name || 'Default User'}
			</span>

			<span class="text-xs capitalize text-[#999999]">
				{!page.data.ossMode
					? (page.data.user as User)?.org_memberships.find(
							(org) => org.organization_id === $activeOrganization?.id
						)?.role ?? 'Unknown'
					: 'ADMIN'}
			</span>
		</div>
	</div>
</a>
