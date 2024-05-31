<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	import SettingsIcon from '$lib/icons/SettingsIcon.svelte';

	const { PUBLIC_IS_LOCAL } = env;

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
				tabHighlightPos = `top: ${currentLink.offsetTop + height - 4}px; left: ${currentLink.offsetLeft}px; width: ${width}px;`;
			}
		}
	}

	onMount(() => {
		moveHighlighter($page.url.pathname);
	});
</script>

<svelte:window on:resize={() => moveHighlighter($page.url.pathname)} />

<section class="relative flex flex-col !h-screen">
	<div class="relative flex flex-col gap-6">
		<h1 class="flex items-center gap-2 pl-8 pr-6 pt-8 pb-0 text-xl font-medium">
			<SettingsIcon class="h-6" />
			Account Settings
		</h1>

		<div
			class="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] px-0 lg:px-8 w-full text-sm font-bold border-b border-[#DDD] data-dark:border-[#2A2A2A]"
		>
			{#each links as { title, href }, index (href)}
				{#if href === '/settings/theme' || PUBLIC_IS_LOCAL === 'false'}
					<a
						bind:this={linkElements[index]}
						{href}
						class="px-6 py-3 {$page.url.pathname.startsWith(href) &&
							'text-secondary'} text-center whitespace-nowrap transition-colors"
					>
						{title}
					</a>
				{/if}
			{/each}

			<div
				style={tabHighlightPos}
				class="absolute bottom-0 h-1 w-1/5 bg-secondary transition-[top,left]"
			/>
		</div>
	</div>

	<slot />
</section>
