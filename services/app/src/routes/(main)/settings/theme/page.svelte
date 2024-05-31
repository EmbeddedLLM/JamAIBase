<script lang="ts">
	import { preferredTheme } from '$globalStore';

	import CheckIcon from '$lib/icons/CheckIcon.svelte';
	import LightMode from '$lib/assets/light-mode.svg';
	import DarkMode from '$lib/assets/dark-mode.svg';
	import SystemMode from '$lib/assets/system-mode.svg';
</script>

<svelte:head>
	<title>Appearance - Settings</title>
</svelte:head>

<div class="grow flex flex-col gap-4 p-6 pt-4 pl-8 min-h-0 overflow-auto">
	<h3 class="font-bold">Appearance</h3>

	<div class="grow grid grid-rows-3 md:grid-cols-3 gap-2 md:gap-8 pr-4 min-h-0 h-min w-full">
		<div class="flex flex-col gap-3 h-min max-w-[65%] md:max-w-none">
			<button on:click={() => ($preferredTheme = 'LIGHT')} class="!block text-start cursor-pointer">
				<div
					class="relative min-h-0 after:content-[''] after:absolute after:top-0 after:left-0 after:right-0 after:bottom-0 after:border-4 after:border-[#0096EB] after:rounded-xl after:[box-shadow:0px_0px_8px_0px_#0096eb80] after:opacity-0 after:transition-opacity"
					class:after:opacity-100={$preferredTheme == 'LIGHT'}
				>
					<img src={LightMode} alt="" />
				</div>
			</button>

			<div class="flex items-center font-medium">
				<CheckIcon
					class={`absolute h-5 stroke-[3] stroke-[#0096EB] ${
						$preferredTheme == 'LIGHT' ? 'opacity-100' : 'opacity-0'
					} transition-opacity duration-300`}
				/>
				<span
					class={`${
						$preferredTheme == 'LIGHT' ? 'text-[#0096EB] translate-x-7' : ''
					} transition-[transform,color] duration-300`}
				>
					Light
				</span>
			</div>
		</div>

		<div class="flex flex-col gap-3 h-min max-w-[65%] md:max-w-none">
			<button on:click={() => ($preferredTheme = 'DARK')} class="!block text-start cursor-pointer">
				<div
					class="relative after:content-[''] after:absolute after:top-0 after:left-0 after:right-0 after:bottom-0 after:border-4 after:border-[#0096EB] after:rounded-xl after:[box-shadow:0px_0px_8px_0px_#0096eb80] after:opacity-0 after:transition-opacity"
					class:after:opacity-100={$preferredTheme == 'DARK'}
				>
					<img src={DarkMode} alt="" />
				</div>
			</button>

			<div class="flex items-center font-medium">
				<CheckIcon
					class={`absolute h-5 stroke-[3] stroke-[#0096EB] ${
						$preferredTheme == 'DARK' ? 'opacity-100' : 'opacity-0'
					} transition-opacity duration-300`}
				/>
				<span
					class={`${
						$preferredTheme == 'DARK' ? 'text-[#0096EB] translate-x-7' : ''
					} transition-[transform,color] duration-300`}
				>
					Dark
				</span>
			</div>
		</div>

		<div class="flex flex-col gap-3 h-min max-w-[65%] md:max-w-none">
			<button
				on:click={() => ($preferredTheme = 'SYSTEM')}
				class="!block text-start cursor-pointer"
			>
				<div
					class="relative after:content-[''] after:absolute after:top-0 after:left-0 after:right-0 after:bottom-0 after:border-4 after:border-[#0096EB] after:rounded-xl after:[box-shadow:0px_0px_8px_0px_#0096eb80] after:opacity-0 after:transition-opacity"
					class:after:opacity-100={$preferredTheme == 'SYSTEM'}
				>
					<img src={SystemMode} alt="" />
				</div>
			</button>

			<div class="flex items-center font-medium">
				<CheckIcon
					class={`absolute h-5 stroke-[3] stroke-[#0096EB] ${
						$preferredTheme == 'SYSTEM' ? 'opacity-100' : 'opacity-0'
					} transition-opacity duration-300`}
				/>
				<span
					class={`${
						$preferredTheme == 'SYSTEM' ? 'text-[#0096EB] translate-x-7' : ''
					} transition-[transform,color] duration-300`}
				>
					Auto
				</span>
			</div>
		</div>
	</div>
</div>
