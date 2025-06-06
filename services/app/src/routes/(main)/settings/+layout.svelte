<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	import SettingsIcon from '$lib/icons/SettingsIcon.svelte';

	const links = [
		{
			title: 'Account',
			href: '/settings/account'
		}
	];

	let linkElements: HTMLAnchorElement[] = [];
	let tabHighlightPos = '';
	$: moveHighlighter($page.url.pathname);
	function moveHighlighter(pathname: string) {
		if (linkElements.length !== 0) {
			const currentLink = [...linkElements]
				.filter((i) => i)
				.find((el) => pathname.startsWith(el.getAttribute('href')!));
			if (currentLink) {
				const { height, width } = currentLink.getBoundingClientRect();
				tabHighlightPos = `top: ${currentLink.offsetTop + height - 3}px; left: ${currentLink.offsetLeft}px; width: ${width}px;`;
			}
		}
	}
	onMount(() => {
		moveHighlighter($page.url.pathname);
	});
</script>

<svelte:window on:resize={() => moveHighlighter($page.url.pathname)} />

<div
	class="absolute top-4 left-1/2 -translate-x-1/2 md:hidden flex items-center gap-2 text-[#344054]"
>
	<h1 class="text-xl whitespace-nowrap">Account Settings</h1>
</div>

<section class="relative flex flex-col h-[calc(100vh-54px)] md:h-screen">
	<div class="relative flex flex-col gap-6">
		<div class="hidden md:flex items-center gap-2 md:pt-8 pb-0 pl-8 pr-6 text-[#344054]">
			<SettingsIcon class="h-8" />
			<h1 class="text-xl">Account Settings</h1>
		</div>

		<div
			class="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] px-0 lg:px-8 w-full text-sm font-bold border-b border-[#E5E5E5] data-dark:border-[#2A2A2A]"
		>
			{#each links as { title, href }, index (href)}
				{#if href === '/settings/theme' || PUBLIC_IS_LOCAL === 'false'}
					<a
						bind:this={linkElements[index]}
						{href}
						class="px-6 py-2 {$page.url.pathname.startsWith(href)
							? 'text-[#344054] font-medium'
							: 'text-[#98A2B3]'} text-center whitespace-nowrap transition-colors"
					>
						{title}
					</a>
				{/if}
			{/each}

			<div
				style={tabHighlightPos}
				class="absolute bottom-0 h-[3px] w-1/5 bg-secondary transition-[top,left]"
			></div>
		</div>
	</div>

	<slot />
</section>
