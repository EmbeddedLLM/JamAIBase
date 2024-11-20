<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { onMount } from 'svelte';
	import Compass from 'lucide-svelte/icons/compass';
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { preferredTheme, showDock } from '$globalStore';
	import { cn } from '$lib/utils';
	import type { PageData } from '../$types';
	import type { SideDockItem } from '$lib/types';

	import longWhiteLogo from '$lib/assets/Jamai-Long-White-Main.svg';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';

	import UserDetails from './UserDetails.svelte';
	import { Button } from '$lib/components/ui/button';
	import SideBarIcon from '$lib/icons/SideBarIcon.svelte';
	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import StickyNoteIcon from '$lib/icons/StickyNoteIcon.svelte';
	import ExternalLinkIcon from '$lib/icons/ExternalLinkIcon.svelte';
	import HomeIcon from '$lib/icons/HomeIcon.svelte';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import LogoutIcon from '$lib/icons/LogoutIcon.svelte';

	export let organizationData: PageData['organizationData'];

	let windowWidth: number;

	$: currentTheme = $preferredTheme == 'DARK' ? 'dark' : 'light';
	$: if (browser) {
		if ($preferredTheme == 'SYSTEM') {
			currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';
		}
	}

	let items: SideDockItem[];
	$: items = [
		{
			type: 'link',
			title: 'Home',
			href: '/home',
			iconClass: '[&_path]:stroke-[1.7]',
			Icon: HomeIcon,
			excludeFromLocal: true
		},
		{
			type: 'link',
			title: 'Project',
			href: '/project',
			iconClass:
				'ml-px h-4 w-4 group-data-[expanded=false]:ml-0 group-data-[expanded=false]:h-[18px] group-data-[expanded=false]:w-[18px] [&_*]:!stroke-[1.1]',
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
			title: ''
		},
		{
			type: 'link',
			title: 'Docs',
			href: 'https://docs.jamaibase.com/',
			openNewTab: true,
			iconClass: '[&_path]:!stroke-[0.2]',
			Icon: StickyNoteIcon,
			EndIcon: ExternalLinkIcon
		}
	];

	let linkElements: HTMLAnchorElement[] = [];
	let tabHighlightPos = '';
	$: $showDock, $page.url.pathname, moveHighlighter();
	async function moveHighlighter() {
		await new Promise((r) => setTimeout(r, 120));
		if (linkElements.length) {
			const currentLink = [...linkElements]
				.filter((i) => i)
				.find((el) => $page.url.pathname.startsWith(el.getAttribute('href')!));
			if (currentLink) {
				tabHighlightPos = `top: ${currentLink.offsetTop}px;`;
			} else {
				tabHighlightPos = 'display: none;';
			}
		}
	}
	onMount(() => {
		moveHighlighter();
	});

	afterNavigate(() => {
		if (windowWidth < 768) {
			$showDock = false;
		}
	});
</script>

<svelte:window bind:innerWidth={windowWidth} />

<!-- svelte-ignore a11y-no-static-element-interactions -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<div
	on:click={() => ($showDock = false)}
	class="block md:hidden absolute top-0 bottom-0 left-0 right-0 z-[999] bg-black {$showDock
		? 'opacity-50'
		: 'opacity-0 pointer-events-none'} transition-opacity duration-200"
/>

<div
	inert={windowWidth !== undefined && windowWidth < 768 && !$showDock}
	class="fixed md:static top-0 bottom-0 left-0 z-[9999] md:z-[1] transition-transform duration-300 {$showDock
		? 'translate-x-0'
		: '-translate-x-full md:translate-x-0'}"
>
	<nav
		class="z-[1] flex flex-col h-full max-h-screen w-[250px] md:w-auto bg-white data-dark:bg-[#303338] border-r border-[#DDD] data-dark:border-[#2A2A2A] transition-[border-radius] duration-500"
	>
		<div
			class="flex justify-between py-4 mb-4 {$showDock
				? 'md:mb-4 px-4'
				: 'md:mb-2'} transition-[margin,padding] duration-200"
		>
			<img
				width="116"
				src={currentTheme == 'dark' ? longWhiteLogo : longBlackLogo}
				alt=""
				class="{$showDock
					? 'md:scale-100'
					: 'md:scale-0 w-0'} transition-[transform,width] duration-300"
			/>

			<Button
				variant="ghost"
				title="Show/hide side navigation bar"
				on:click={() => ($showDock = !$showDock)}
				class="flex-[0_0_auto] p-0 h-12 w-12 aspect-square rounded-full {$showDock
					? 'md:translate-x-0'
					: 'md:-translate-x-[3.5px]'} transition-[transform,background-color] duration-200 group"
			>
				<SideBarIcon class="scale-125 [&_*]:stroke-[1.3]" />
			</Button>
		</div>

		<div
			data-expanded={$showDock}
			class="relative flex flex-col grow pb-2 {$showDock
				? 'px-1'
				: 'px-0'} transition-[padding,margin] duration-300 overflow-x-hidden overflow-y-auto group"
		>
			{#each items as item}
				{#if !(item.excludeFromLocal && PUBLIC_IS_LOCAL !== 'false')}
					{#if item.type === 'category'}
						{#if item.title}
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
							<hr
								class="-mx-1 my-1 border-[#E5E5E5] data-dark:border-[#484C55] transition-[margin]"
							/>
						{/if}
					{:else}
						{@const { Icon, EndIcon, iconClass } = item}
						{@const linkIndex = items
							.filter((i) => i.type === 'link')
							.findIndex((i) => JSON.stringify(i) === JSON.stringify(item))}
						<a
							title={item.title}
							target={item.openNewTab ? '_blank' : ''}
							href={item.href}
							bind:this={linkElements[linkIndex]}
							class="flex-[0_0_auto] relative flex items-center w-full {$showDock
								? 'gap-2 px-4 py-3 h-9 rounded-md'
								: 'gap-0 p-3 h-11'} {$page.url.pathname.startsWith(item.href) &&
								'!bg-[#FFEFF2]'} hover:bg-[#F2F4F7] data-dark:hover:bg-white/[0.04] text-[#344054] data-dark:text-white whitespace-nowrap transition-all"
						>
							<Icon
								class={cn(
									`absolute flex-[0_0_auto] h-[18px] w-[18px] group-data-[expanded=false]:h-[22px] group-data-[expanded=false]:w-[22px] ${
										$showDock
											? 'left-4 duration-100'
											: 'left-1/2 -translate-x-1/2 duration-200 delay-150'
									} transition-all [&_path]:stroke-[1.5] ${
										$page.url.pathname.startsWith(item.href)
											? 'text-[#950048]'
											: 'text-[#344054] data-dark:text-white'
									}`,
									iconClass
								)}
							/>
							<span
								class="absolute left-12 {$showDock
									? 'opacity-100'
									: 'opacity-0 pointer-events-none'} {$page.url.pathname.startsWith(item.href)
									? 'text-[#950048]'
									: 'text-[#344054] data-dark:text-white'} text-sm font-medium transition-[opacity,left] duration-200"
							>
								{item.title}
							</span>

							{#if EndIcon}
								<EndIcon
									class="ml-auto h-[18px] w-[18px] flex-[0_0_auto] transition-all [&_path]:stroke-[1.5] {$showDock
										? 'opacity-100'
										: 'opacity-0'}"
								/>
							{/if}
						</a>
					{/if}
				{/if}
			{/each}

			{#if PUBLIC_IS_LOCAL === 'false'}
				<hr class="-mx-1 my-1 border-[#E5E5E5] data-dark:border-[#484C55] transition-[margin]" />

				<a
					title="Log Out"
					href="/logout"
					bind:this={linkElements[4]}
					class="flex-[0_0_auto] relative flex items-center w-full {$showDock
						? 'px-4 py-3 h-9 rounded-md'
						: 'p-3 h-11'} {$page.url.pathname.startsWith('/logout') &&
						'!bg-[#FFEFF2]'} hover:bg-[#F2F4F7] data-dark:hover:bg-white/[0.04] text-[#666] data-dark:text-white whitespace-nowrap transition-all"
				>
					<LogoutIcon
						class="absolute flex-[0_0_auto] {$showDock
							? 'left-4 h-4 w-4 duration-100'
							: 'left-1/2 -translate-x-1/2 h-[20px] w-[20px] duration-200 delay-150'} transition-all {$page.url.pathname.startsWith(
							'/logout'
						)
							? 'text-secondary'
							: 'text-[#344054] data-dark:text-white'} [&_path]:stroke-[1.2]"
					/>
					<span
						class="absolute left-12 {$showDock
							? 'opacity-100'
							: 'opacity-0 pointer-events-none'} {$page.url.pathname.startsWith('/logout')
							? 'text-secondary'
							: 'text-[#344054] data-dark:text-white'} text-sm font-medium transition-[opacity,left] duration-200"
					>
						Log Out
					</span>
				</a>

				<hr class="-mx-1 mt-1 border-[#E5E5E5] data-dark:border-[#484C55]" />
			{/if}

			<!-- Highlighter -->
			<div
				style={tabHighlightPos}
				class="{$showDock
					? 'opacity-0 [transition:top_150ms]'
					: 'opacity-100 [transition:top_150ms,_opacity_150ms_ease-in-out_160ms]'} absolute left-0 h-11 w-[3px] bg-[#950048]"
			/>
		</div>

		{#if organizationData?.tier === 'free'}
			<div
				class="self-center flex flex-col items-center gap-3 p-4 mb-4 w-[calc(100%_-_32px)] text-sm text-center bg-[#F3F6FF] data-dark:bg-zinc-700 rounded-xl overflow-hidden whitespace-nowrap {$showDock
					? 'md:opacity-100'
					: 'md:opacity-0'} transition-opacity"
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
</div>
