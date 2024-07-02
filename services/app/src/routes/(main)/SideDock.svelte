<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { preferredTheme, showDock } from '$globalStore';
	import type { PageData } from '../$types';
	import type { SideDockItem } from '$lib/types';

	import longWhiteLogo from '$lib/assets/Jamai-Long-White-Main.svg';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';

	import UserDetails from './UserDetails.svelte';
	import { Button } from '$lib/components/ui/button';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import StickyNoteIcon from '$lib/icons/StickyNoteIcon.svelte';
	import ExternalLinkIcon from '$lib/icons/ExternalLinkIcon.svelte';
	import HomeIcon from '$lib/icons/HomeIcon.svelte';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import LogoutIcon from '$lib/icons/LogoutIcon.svelte';

	export let organizationData: PageData['organizationData'];

	$: currentTheme = $preferredTheme == 'DARK' ? 'dark' : 'light';
	$: if (browser) {
		if ($preferredTheme == 'SYSTEM') {
			currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';
		}
	}

	let items: SideDockItem[];
	$: items = [
		{
			type: 'category',
			title: 'HOME'
		},
		{
			type: 'link',
			title: 'Dashboard',
			href: '/dashboard',
			Icon: HomeIcon,
			excludeFromLocal: true
		},
		{
			type: 'link',
			title: 'Project',
			href: '/project',
			Icon: AssignmentIcon
		},
		{
			type: 'link',
			title: 'Organization',
			href: '/organization',
			Icon: PeopleIcon,
			excludeFromLocal: true
		},
		{
			type: 'category',
			title: 'DOCUMENTATION'
		},
		{
			type: 'link',
			title: 'Docs',
			href: 'https://docs.jamaibase.com/',
			openNewTab: true,
			Icon: StickyNoteIcon,
			EndIcon: ExternalLinkIcon
		}
	];

	let linkElements: HTMLAnchorElement[] = [];
	let tabHighlightPos = '';
	$: moveHighlighter($showDock, $page.url.pathname);
	async function moveHighlighter(showDock: boolean, pathname: string) {
		const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
		await sleep(200);
		if (linkElements.length) {
			const currentLink = [...linkElements]
				.filter((i) => i)
				.find((el) => $page.url.pathname.startsWith(el.getAttribute('href')!));
			if (currentLink) {
				tabHighlightPos = `top: ${currentLink.offsetTop - ($showDock ? 0 : 12)}px;`;
			} else {
				tabHighlightPos = 'display: none;';
			}
		}
	}
</script>

<nav
	class="z-[1] flex flex-col h-full bg-white data-dark:bg-[#303338] border-r border-[#DDD] data-dark:border-[#2A2A2A] overflow-hidden transition-[border-radius] duration-500"
>
	<div class="flex justify-between px-6 py-4 mb-4">
		<img
			width="116"
			src={currentTheme == 'dark' ? longWhiteLogo : longBlackLogo}
			alt=""
			class="{$showDock ? 'scale-100' : 'scale-0'} transition-transform duration-200"
		/>

		<Button
			variant="ghost"
			on:click={() => ($showDock = !$showDock)}
			class="flex-[0_0_auto] p-0 h-12 w-12 aspect-square rounded-full {$showDock
				? 'translate-x-0'
				: '-translate-x-8'} transition-[transform,background-color,top,right] duration-200"
		>
			<HamburgerIcon class="h-7 w-7" />
		</Button>
	</div>

	<div class="relative flex flex-col grow pb-2 transition-[padding,margin] duration-300">
		{#each items as item}
			{#if !(item.excludeFromLocal && PUBLIC_IS_LOCAL !== 'false')}
				{#if item.type === 'category'}
					<div
						class="{$showDock
							? 'pl-5 [&:not(:first-child)]:mt-3 [&:not(:first-child)]:pt-3'
							: 'pl-3 [&:not(:first-child)]:mt-0 [&:not(:first-child)]:pt-0'} mb-1 text-sm text-[#999] font-medium [&:not(:first-child)]:border-t border-[#E5E5E5] data-dark:border-[#484C55] cursor-default transition-[padding,margin] duration-200"
					>
						<span class="{$showDock ? 'opacity-100' : 'opacity-0'} transition-opacity">
							{item.title}
						</span>
					</div>
				{:else}
					{@const { Icon, EndIcon } = item}
					{@const linkIndex = items
						.filter((i) => i.type === 'link')
						.findIndex((i) => JSON.stringify(i) === JSON.stringify(item))}
					<a
						title={item.title}
						target={item.openNewTab ? '_blank' : '_self'}
						href={item.href}
						bind:this={linkElements[linkIndex]}
						class="relative flex items-center h-12 w-full {$showDock
							? 'gap-2 px-4 py-3'
							: 'gap-0 p-3 -translate-y-3'} {$page.url.pathname.startsWith(item.href) &&
							'!bg-secondary/20'} hover:bg-black/[0.04] data-dark:hover:bg-white/[0.04] text-[#666] data-dark:text-white whitespace-nowrap transition-all"
					>
						<Icon
							class="absolute flex-[0_0_auto] {$showDock
								? 'left-4 h-5 w-5 duration-100'
								: 'left-1/2 -translate-x-1/2 h-6 w-6 duration-200 delay-200'} transition-all [&_path]:stroke-[1.5] {$page.url.pathname.startsWith(
								item.href
							)
								? 'text-secondary'
								: 'text-[#666] data-dark:text-white'}"
						/>
						<span
							class="absolute left-12 {$showDock
								? 'opacity-100'
								: 'opacity-0 pointer-events-none'} {$page.url.pathname.startsWith(item.href)
								? 'text-secondary'
								: 'text-[#666] data-dark:text-white'} text-sm font-medium transition-[opacity,left] duration-200"
						>
							{item.title}
						</span>

						{#if EndIcon}
							<EndIcon
								class="ml-auto h-5 w-5 flex-[0_0_auto] transition-all [&_path]:stroke-[1.5] {$showDock
									? 'opacity-100'
									: 'opacity-0'}"
							/>
						{/if}
					</a>
				{/if}
			{/if}
		{/each}

		{#if PUBLIC_IS_LOCAL === 'false'}
			<hr
				class="{$showDock
					? 'mt-3'
					: 'mt-0'} mb-1 border-[#E5E5E5] data-dark:border-[#484C55] transition-[margin]"
			/>

			<a
				title="Log Out"
				href="/logout"
				bind:this={linkElements[4]}
				class="relative flex items-center h-12 w-full {$showDock
					? 'gap-2 px-4 py-3'
					: 'gap-0 p-3'} {$page.url.pathname.startsWith('/logout') &&
					'!bg-secondary/20'} hover:bg-black/[0.04] data-dark:hover:bg-white/[0.04] text-[#666] data-dark:text-white whitespace-nowrap transition-all"
			>
				<LogoutIcon
					class="absolute flex-[0_0_auto] {$showDock
						? 'left-4 h-5 w-5 duration-100'
						: 'left-1/2 -translate-x-1/2 h-6 w-6 duration-200 delay-200'} transition-all [&_path]:stroke-[1.5] {$page.url.pathname.startsWith(
						'/logout'
					)
						? 'text-secondary'
						: 'text-[#666] data-dark:text-white'}"
				/>
				<span
					class="absolute left-12 {$showDock
						? 'opacity-100'
						: 'opacity-0 pointer-events-none'} {$page.url.pathname.startsWith('/logout')
						? 'text-secondary'
						: 'text-[#666] data-dark:text-white'} text-sm font-medium transition-[opacity,left] duration-200"
				>
					Log Out
				</span>
			</a>

			<hr class="mt-1 border-[#E5E5E5] data-dark:border-[#484C55]" />
		{/if}

		<!-- Highlighter -->
		<div style={tabHighlightPos} class="absolute left-0 h-12 w-1 bg-secondary transition-[top]" />
	</div>

	{#if $showDock && organizationData?.tier === 'free'}
		<div
			class="self-center flex flex-col items-center gap-3 p-4 mb-4 w-max text-sm text-center bg-[#F3F6FF] data-dark:bg-zinc-700 rounded-xl"
		>
			Ready for more? <br /> Upgrade to our premium plan
			<Button class="px-8 h-9 rounded-full">
				<a href="https://jamaibase.com/pricing" target="_blank"> Upgrade Plan </a>
			</Button>
		</div>
	{/if}

	<hr class="border-[#DDD] data-dark:border-[#454545]" />

	<UserDetails />
</nav>
