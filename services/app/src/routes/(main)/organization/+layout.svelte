<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';

	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';

	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();

	const links = [
		{
			title: 'General',
			href: '/organization/general'
		},
		{
			title: 'Team',
			href: '/organization/team'
		},
		{
			title: 'Secrets',
			href: '/organization/secrets'
		},
		{
			title: 'Billing',
			href: '/organization/billing',
			exclude: page.data.ossMode
		},
		{
			title: 'Usage',
			href: '/organization/usage'
		}
	];

	let linkElements: HTMLAnchorElement[] = $state([]);
	let tabHighlightPos = $state('');
	function moveHighlighter(pathname: string) {
		if (linkElements.length) {
			const currentLink = [...linkElements]
				.filter((i) => i)
				.find((el) => pathname.startsWith(el.getAttribute('href')!));

			if (currentLink) {
				const { height, width } = currentLink.getBoundingClientRect();
				tabHighlightPos = `top: ${currentLink.offsetTop + height - 2}px; left: ${currentLink.offsetLeft}px; width: ${width}px;`;
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

<section class="relative flex h-1 grow flex-col">
	<div class="relative flex flex-col gap-2 md:mt-3">
		<div class="flex items-center gap-2 pl-8 pt-0.5 text-[#344054]">
			<PeopleIcon class="h-6" />
			<h1 class="text-xl">Organization</h1>
		</div>

		<div
			data-testid="organization-nav"
			class="grid w-full grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] border-b border-[#E5E5E5] px-0 text-sm data-dark:border-[#2A2A2A] xxs:grid-cols-[repeat(5,minmax(4.5rem,1fr))] sm:grid-cols-[repeat(auto-fill,minmax(6rem,1fr))] lg:px-8"
		>
			{#each links.filter((l) => !l.exclude) as { title, href }, index (href)}
				<a
					bind:this={linkElements[index]}
					{href}
					class="px-2 py-2 sm:px-4 {page.url.pathname.startsWith(href)
						? 'font-medium text-[#333]'
						: 'text-[#999]'} whitespace-nowrap text-center transition-colors"
				>
					{title}
				</a>
			{/each}

			<div
				style={tabHighlightPos}
				class="absolute bottom-0 h-[2px] w-1/5 bg-secondary transition-[top,left]"
			></div>
		</div>
	</div>

	{@render children?.()}
</section>
