<script lang="ts">
	import { MediaQuery } from 'svelte/reactivity';
	import { signOut } from '@auth/sveltekit/client';
	import {
		ChartLine,
		CircleDollarSign,
		Clipboard,
		Compass,
		CpuIcon,
		MessageCircle,
		Sparkle
	} from '@lucide/svelte';
	import { browser } from '$app/environment';
	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/state';
	import { preferredTheme, showDock } from '$globalStore';
	import { cn } from '$lib/utils';
	import type { OrganizationReadRes, SideDockItem } from '$lib/types';

	import longWhiteLogo from '$lib/assets/Jamai-Long-White-Main.svg';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';

	import UserDetails from './UserDetails.svelte';
	import { m } from '$lib/paraglide/messages';
	import { Button } from '$lib/components/ui/button';
	import SideBarIcon from '$lib/icons/SideBarIcon.svelte';
	import StickyNoteIcon from '$lib/icons/StickyNoteIcon.svelte';
	import ExternalLinkIcon from '$lib/icons/ExternalLinkIcon.svelte';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import LogoutIcon from '$lib/icons/LogoutIcon.svelte';

	let { organizationData }: { organizationData?: OrganizationReadRes } = $props();

	const bigScreen = new MediaQuery('min-width: 768px', true);

	let isInSystemPages = $derived(page.url.pathname.startsWith('/system'));
	let currentTheme = $derived($preferredTheme == 'DARK' ? 'dark' : 'light');
	$effect(() => {
		if (browser) {
			if ($preferredTheme == 'SYSTEM') {
				currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';
			}
		}
	});

	const items = [
		{
			type: 'category',
			title: 'ORGANIZATION'
		},
		{
			type: 'link',
			title: m['left_dock.project'](),
			href: '/project',
			iconClass:
				'ml-px h-4 w-4 group-data-[expanded=false]:ml-0 group-data-[expanded=false]:h-[18px] group-data-[expanded=false]:w-[18px] [&_*]:!stroke-[2]',
			Icon: Clipboard
		},
		{
			type: 'link',
			title: m['left_dock.analytics'](),
			href: '/analytics',
			iconClass: '[&_path]:stroke-[1.7]',
			Icon: ChartLine
		},
		{
			type: 'link',
			title: 'Discover Templates',
			href: '/template',
			Icon: Compass,
			exclude: page.data.ossMode
		},
		{
			type: 'link',
			title: m['left_dock.organization'](),
			href: '/organization',
			Icon: PeopleIcon
		},
		{
			type: 'category',
			title: 'SUPPORT'
		},
		{
			type: 'link',
			title: m['left_dock.docs'](),
			href: 'https://docs.jamaibase.com/',
			openNewTab: true,
			iconClass: '[&_path]:!stroke-[0.2]',
			Icon: StickyNoteIcon,
			EndIcon: ExternalLinkIcon
		}
	] as SideDockItem[];

	const systemItems = [
		{
			type: 'link',
			title: 'Model Setup',
			href: '/system/models',
			Icon: CpuIcon
		},
		{
			type: 'link',
			title: 'Price Plans',
			href: '/system/prices',
			Icon: CircleDollarSign,
			exclude: page.data.ossMode
		}
		// {
		// 	type: 'link',
		// 	title: 'Template Studio',
		// 	href: '/system/templates',
		// 	Icon: Sparkle
		// }
	] as SideDockItem[];

	// let linkElements = new SvelteMap<string, HTMLAnchorElement>();
	// let tabHighlightPos = $state('');
	// $effect(() => {
	// 	$showDock;
	// 	page.url.pathname, moveHighlighter();
	// });
	// async function moveHighlighter() {
	// 	await new Promise((r) => setTimeout(r, 120));
	// 	if (linkElements.size) {
	// 		const currentLink = linkElements
	// 			.entries()
	// 			.filter((i) => i)
	// 			.find((el) => page.url.pathname.startsWith(el[1].getAttribute('href')!));
	// 		if (currentLink) {
	// 			tabHighlightPos = `display: block; top: ${currentLink[1].offsetTop}px;`;
	// 		} else {
	// 			tabHighlightPos = 'display: none;';
	// 		}
	// 	}
	// }
	// onMount(() => {
	// 	moveHighlighter();
	// });

	afterNavigate(() => {
		if (!bigScreen.current) {
			$showDock = false;
		}
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	onclick={() => ($showDock = false)}
	class="absolute bottom-0 left-0 right-0 top-0 z-[999] block bg-black md:hidden {$showDock
		? 'opacity-50'
		: 'pointer-events-none opacity-0'} transition-opacity duration-200"
></div>

<div
	inert={!bigScreen.current && !$showDock}
	class="fixed bottom-0 left-0 top-0 z-[9999] transition-transform duration-300 md:static md:z-[1] md:py-3 md:pl-3 {$showDock
		? 'translate-x-0'
		: '-translate-x-full md:translate-x-0'}"
>
	<nav
		class="z-[1] flex h-full max-h-screen w-[250px] flex-col border-r border-[#DDD] bg-white transition-[border-radius] duration-500 data-dark:border-[#2A2A2A] data-dark:bg-[#303338] md:max-h-[calc(100vh-24px)] md:w-auto {$showDock
			? 'md:rounded-2xl'
			: 'md:rounded-[32px]'} md:border-r-transparent md:shadow-[0px_1px_4px_0px_#1018281A]"
	>
		<div
			class={cn(
				'flex justify-between py-4 transition-[margin,padding] duration-200',
				$showDock ? 'px-4' : 'md:mb-2'
			)}
		>
			<img
				width="116"
				src={currentTheme == 'dark' ? longWhiteLogo : longBlackLogo}
				alt=""
				class="{$showDock || !bigScreen.current
					? 'md:scale-100'
					: 'w-0 md:scale-0'} transition-[transform,width] duration-300"
			/>

			<Button
				variant="ghost"
				title={m['left_dock.show_hide_btn']()}
				onclick={() => ($showDock = !$showDock)}
				class="aspect-square h-12 w-12 flex-[0_0_auto] rounded-full p-0 {$showDock
					? 'md:translate-x-0'
					: 'md:-translate-x-[3.5px]'} group transition-[transform,background-color] duration-200"
			>
				<SideBarIcon class="scale-125 [&_*]:stroke-[1.3]" />
			</Button>
		</div>

		<div
			data-expanded={$showDock}
			class="relative flex grow flex-col pb-2 {$showDock || !bigScreen.current
				? 'px-2'
				: 'px-1'} group overflow-y-auto overflow-x-hidden transition-[padding,margin] duration-300"
		>
			<a
				title="Switch to JamAI Chat"
				href="/chat"
				style="background: linear-gradient(224.34deg, #e280a3 15.61%, #ffc1d7 49.6%, #e280a3 83.58%); box-shadow: 0px 1px 3px 0px rgba(16, 24, 40, 0.1);;"
				class={cn(
					'group/link relative flex w-full flex-[0_0_auto] items-center whitespace-nowrap p-px text-[#A62050] transition-[height,width,transform,border-radius]',
					$showDock || !bigScreen.current
						? 'h-9 rounded-md'
						: 'h-11 w-11 translate-x-[1.5px] rounded-[50%]',
					isInSystemPages && 'invisible h-4 opacity-0'
				)}
			>
				<div
					style="background: linear-gradient(267.77deg, #FFEFF2 45.75%, #FFF7DD 100%);"
					class={cn(
						'flex h-full w-full flex-[0_0_auto] items-center transition-all',
						$showDock || !bigScreen.current
							? 'gap-2 rounded-[calc(var(--radius)_-_3px)] px-4 py-3'
							: 'gap-0 rounded-[50%]'
					)}
				>
					<MessageCircle
						class={cn(
							'absolute h-[18px] w-[18px] flex-[0_0_auto] group-data-[expanded=false]:h-[22px] group-data-[expanded=false]:w-[22px] [&_path]:stroke-[1.5]',
							$showDock || !bigScreen.current
								? 'left-4 [transition:height_100ms_ease-in-out,_width_100ms_ease-in-out,_left_100ms_ease-in-out,_transform_100ms_ease-in-out,_color_150ms]'
								: 'left-1/2 -translate-x-1/2 [transition:height_200ms_ease-in-out,_width_200ms_ease-in-out,_left_200ms_ease-in-out_150ms,_transform_200ms_ease-in-out_150ms,_color_150ms]'
						)}
					/>

					<span
						class={cn(
							'absolute left-12 text-sm font-medium transition-[opacity,left] duration-200',
							$showDock ? 'opacity-100' : 'pointer-events-none opacity-0'
						)}
					>
						Switch to JamAI Chat
					</span>
				</div>
			</a>

			{#each isInSystemPages ? systemItems : items as item}
				{#if !item.exclude}
					{#if item.type === 'category'}
						{#if item.title}
							<div
								class="{$showDock || !bigScreen.current
									? 'pl-3 [&:not(:first-child)]:mt-3 [&:not(:first-child)]:pt-3'
									: 'pl-3 [&:not(:first-child)]:mt-0 [&:not(:first-child)]:pt-0'} mb-1 cursor-default border-[#E5E5E5] text-sm font-medium text-[#98A2B3] transition-[padding,margin] duration-200 data-dark:border-[#484C55]"
							>
								<span class="{$showDock ? 'opacity-100' : 'opacity-0'} transition-opacity">
									{item.title}
								</span>
							</div>
						{:else}
							<hr class="my-1 border-[#E5E5E5] transition-[margin] data-dark:border-[#484C55]" />
						{/if}
					{:else}
						{@const { Icon, EndIcon, iconClass } = item}
						<a
							title={item.title}
							target={item.openNewTab ? '_blank' : ''}
							href={item.href}
							class={cn(
								'group/link relative flex w-full flex-[0_0_auto] items-center whitespace-nowrap text-[#344054] transition-all data-dark:text-white',
								$showDock || !bigScreen.current
									? 'h-9 gap-2 rounded-md px-4 py-3 hover:bg-[#F2F4F7] data-dark:hover:bg-white/[0.04]'
									: 'h-11 gap-0 p-3',
								$showDock &&
									page.url.pathname.startsWith(item.href) &&
									(isInSystemPages ? '!bg-[#E8FAFB]' : '!bg-[#FFEFF2]')
							)}
						>
							<div
								class={cn(
									'absolute left-[1.5px] h-11 w-11 rounded-full',
									$showDock
										? 'opacity-0 [transition:opacity_100ms_ease-in-out,_background-color_150ms]'
										: 'opacity-100 [transition:opacity_150ms_ease-in-out_160ms,_background-color_150ms]',
									page.url.pathname.startsWith(item.href) && !$showDock
										? isInSystemPages
											? 'bg-[#17787E]'
											: 'bg-[#950048]'
										: 'group-hover/link:bg-[#F2F4F7] data-dark:group-hover/link:bg-white/[0.04]'
								)}
							></div>

							<Icon
								class={cn(
									'absolute h-[18px] w-[18px] flex-[0_0_auto] group-data-[expanded=false]:h-[22px] group-data-[expanded=false]:w-[22px] [&_path]:stroke-[1.5]',
									$showDock || !bigScreen.current
										? 'left-4 [transition:left_100ms_ease-in-out,_transform_100ms_ease-in-out,_color_150ms]'
										: 'left-1/2 -translate-x-1/2 [transition:left_200ms_ease-in-out_150ms,_transform_200ms_ease-in-out_150ms,_color_150ms] ',
									page.url.pathname.startsWith(item.href)
										? $showDock || !bigScreen.current
											? isInSystemPages
												? 'text-[#17787E]'
												: 'text-[#950048]'
											: 'text-white'
										: 'text-[#344054] data-dark:text-white',
									iconClass
								)}
							/>
							<span
								class={cn(
									'absolute left-12 text-sm font-medium transition-[opacity,left] duration-200',
									$showDock ? 'opacity-100' : 'pointer-events-none opacity-0',
									page.url.pathname.startsWith(item.href)
										? isInSystemPages
											? 'text-[#17787E]'
											: 'text-[#950048]'
										: 'text-[#344054] data-dark:text-white'
								)}
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

							<!-- Highlighter fallback -->
							<!-- {#if page.url.pathname.startsWith(item.href) && !tabHighlightPos}
								<div
									class={cn(
										'absolute left-0 h-11 w-[3px]',
										$showDock
											? 'opacity-0 [transition:top_150ms]'
											: 'opacity-100 [transition:top_150ms,_opacity_150ms_ease-in-out_160ms]',
										isInSystemPages ? 'bg-[#17787E]' : 'bg-[#950048]'
									)}
								></div>
							{/if} -->
						</a>
					{/if}
				{/if}
			{/each}

			<hr class="my-1 border-[#E5E5E5] transition-[margin] data-dark:border-[#484C55]" />

			{#if !page.data.ossMode}
				<Button
					variant="ghost"
					title={m['left_dock.logout']()}
					onclick={page.data.auth0Mode ? () => goto('/logout') : signOut}
					class="group/link relative flex w-full flex-[0_0_auto] items-center {$showDock ||
					!bigScreen.current
						? 'h-9 rounded-md px-4 py-3'
						: 'h-11 rounded-none p-3 hover:bg-transparent data-dark:hover:bg-transparent'} whitespace-nowrap text-[#666] transition-all data-dark:text-white"
				>
					<div
						class={cn(
							'absolute left-[1.5px] h-11 w-11 rounded-full',
							$showDock
								? 'opacity-0 [transition:opacity_100ms_ease-in-out,_background-color_150ms]'
								: 'opacity-100 [transition:opacity_150ms_ease-in-out_160ms,_background-color_150ms]',

							'group-hover/link:bg-[#F2F4F7] data-dark:group-hover/link:bg-white/[0.04]'
						)}
					></div>

					<LogoutIcon
						class="absolute flex-[0_0_auto] {$showDock || !bigScreen.current
							? 'left-4 h-4 w-4 duration-100'
							: 'left-1/2 h-[20px] w-[20px] -translate-x-1/2 delay-150 duration-200'} text-[#344054] transition-all data-dark:text-white [&_path]:stroke-[1.2]"
					/>
					<span
						class="absolute left-12 {$showDock
							? 'opacity-100'
							: 'pointer-events-none opacity-0'} text-sm font-medium text-[#344054] transition-[opacity,left] duration-200 data-dark:text-white"
					>
						{m['left_dock.logout']()}
					</span>
				</Button>

				<hr class="mt-1 border-[#E5E5E5] data-dark:border-[#484C55]" />
			{/if}

			<!-- Highlighter -->
			<!-- <div
				style={tabHighlightPos}
				class={cn(
					'absolute left-0 hidden h-11 w-[3px]',
					$showDock
						? 'opacity-0 [transition:top_150ms]'
						: 'opacity-100 [transition:top_150ms,_opacity_150ms_ease-in-out_160ms]',
					isInSystemPages ? 'bg-[#17787E]' : 'bg-[#950048]'
				)}
			></div> -->
		</div>

		{#if organizationData?.price_plan?.flat_cost === 0 && !page.url.pathname.startsWith('/system')}
			<div
				class="mb-4 flex max-h-40 w-[calc(100%_-_32px)] flex-col items-center gap-3 self-center overflow-hidden whitespace-nowrap rounded-xl bg-[#F3F6FF] px-2 py-4 text-center text-sm data-dark:bg-zinc-700 {$showDock
					? 'delay-300 md:opacity-100'
					: 'duration-0 md:opacity-0'} transition-opacity"
			>
				<p class="max-w-full whitespace-pre-wrap break-all">
					{@html m['left_dock.upgrade']()}
				</p>
				<Button href="https://jamaibase.com/pricing" target="_blank" class="h-9 px-8">
					{m['left_dock.upgrade_btn']()}
				</Button>
			</div>
		{/if}

		<hr class="border-[#DDD] data-dark:border-[#454545] md:hidden" />

		<UserDetails />
	</nav>
</div>
