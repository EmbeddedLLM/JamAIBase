<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';

	import SettingsIcon from '$lib/icons/SettingsIcon.svelte';

	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();

	const links = [
		{
			title: 'Account',
			href: '/settings/account'
		}
	];

	let linkElements: HTMLAnchorElement[] = $state([]);
	let tabHighlightPos = $state('');
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
		moveHighlighter(page.url.pathname);
	});
	$effect(() => {
		moveHighlighter(page.url.pathname);
	});
</script>

<svelte:window onresize={() => moveHighlighter(page.url.pathname)} />

<div
	class="absolute left-1/2 top-4 flex -translate-x-1/2 items-center gap-2 text-[#344054] md:hidden"
>
	<h1 class="whitespace-nowrap text-xl">Account Settings</h1>
</div>

<section class="relative flex h-[calc(100vh-54px)] flex-col md:h-screen">
	<div class="relative flex flex-col gap-6">
		<div class="hidden items-center gap-2 pb-0 pl-8 pr-6 text-[#344054] md:flex md:pt-8">
			<SettingsIcon class="h-8" />
			<h1 class="text-xl">Account Settings</h1>
		</div>

		<div
			class="grid w-full grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] border-b border-[#E5E5E5] px-0 text-sm font-bold data-dark:border-[#2A2A2A] lg:px-8"
		>
			{#each links as { title, href }, index (href)}
				<a
					bind:this={linkElements[index]}
					{href}
					class="px-6 py-2 {page.url.pathname.startsWith(href)
						? 'font-medium text-[#344054]'
						: 'text-[#98A2B3]'} whitespace-nowrap text-center transition-colors"
				>
					{title}
				</a>
			{/each}

			<div
				style={tabHighlightPos}
				class="absolute bottom-0 h-[3px] w-1/5 bg-secondary transition-[top,left]"
			></div>
		</div>
	</div>

	{@render children?.()}
</section>
