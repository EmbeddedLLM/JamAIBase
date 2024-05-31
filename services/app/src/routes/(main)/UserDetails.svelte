<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { page } from '$app/stores';
	import { showDock } from '$globalStore';

	import UserRole from '$lib/components/UserRole.svelte';

	const { PUBLIC_IS_LOCAL } = env;

	let settingsBtnHasFocus = false;
</script>

<a
	href="/settings"
	class="flex flex-col gap-2 {$showDock
		? 'px-4 py-3'
		: 'p-3'} hover:bg-accent transition-[padding,background] duration-300 {PUBLIC_IS_LOCAL ===
	'false'
		? 'pointer-events-auto'
		: 'pointer-events-none'}"
>
	<div
		class="relative flex {$showDock
			? 'gap-4'
			: 'gap-0'} w-full text-left rounded-lg transition-[gap] duration-300"
	>
		<div class="relative placeholder pointer-events-none select-none rounded-full">
			<div
				class="flex items-center justify-center bg-[#93D48D] rounded-full h-11 w-11 {settingsBtnHasFocus &&
				!$showDock
					? 'outline'
					: 'outline-none'} outline-2 aspect-square overflow-hidden"
			>
				{#if $page.data.user}
					<img src={$page.data.user.picture} alt="User Avatar" class="object-cover w-full h-full" />
				{:else}
					<span class="text-xl text-black uppercase">{'Default User'?.charAt(0)}</span>
				{/if}
			</div>
		</div>

		<div
			class="grow flex flex-col {$showDock
				? 'opacity-100 w-full'
				: 'opacity-0 w-0 pointer-events-none'} transition-[opacity,_width] duration-300"
		>
			<span class="break-all line-clamp-1">
				{$page.data.user?.nickname || 'Default User'}
			</span>
			<UserRole />
		</div>
	</div>
</a>
