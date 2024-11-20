<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { page } from '$app/stores';
	import { activeOrganization, showDock } from '$globalStore';

	let settingsBtnHasFocus = false;
</script>

<a
	href="/settings"
	class="flex flex-col gap-2 px-4 py-3 {$showDock
		? 'sm:px-4 sm:py-3'
		: 'sm:p-3'} hover:bg-accent transition-[padding,background] duration-300 {PUBLIC_IS_LOCAL ===
	'false'
		? 'pointer-events-auto'
		: 'pointer-events-none'}"
>
	<div
		class="relative flex items-center {$showDock
			? 'gap-4'
			: 'gap-0'} w-full text-left rounded-lg transition-[gap] duration-300"
	>
		<div class="relative placeholder pointer-events-none select-none rounded-full">
			<div
				class="flex items-center justify-center bg-[#93D48D] rounded-full h-9 w-9 {settingsBtnHasFocus &&
				!$showDock
					? 'outline'
					: 'outline-none -translate-x-0.5'} outline-2 aspect-square overflow-hidden transition-transform"
			>
				{#if $page.data.user}
					<img src={$page.data.user.picture} alt="User Avatar" class="object-cover w-full h-full" />
				{:else}
					<span class="text-xl text-black uppercase">{'Default User'?.charAt(0)}</span>
				{/if}
			</div>
		</div>

		<div
			class="grow flex flex-col w-auto {$showDock
				? 'sm:opacity-100 sm:w-full'
				: 'sm:opacity-0 sm:w-0 sm:pointer-events-none'} transition-[opacity,_width] duration-300"
		>
			<span class="break-all line-clamp-1">
				{$page.data.user?.nickname || 'Default User'}
			</span>

			<span class="text-xs text-[#999999] capitalize">
				{PUBLIC_IS_LOCAL === 'false' ? $activeOrganization?.role ?? 'Unknown' : 'Admin'}
			</span>
		</div>
	</div>
</a>
