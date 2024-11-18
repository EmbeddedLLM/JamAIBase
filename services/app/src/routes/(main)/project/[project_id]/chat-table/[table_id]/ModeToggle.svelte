<script lang="ts">
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import { cn } from '$lib/utils';
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher<{
		checkedChange: { event: MouseEvent; value: boolean };
	}>();

	let className: string | undefined | null = undefined;
	export { className as class };

	export let id: string | undefined = undefined;
	export let defaultChecked: boolean = false;
	export let disabled: boolean | undefined = undefined;
	export let required: boolean | undefined = undefined;
	export let name: string | undefined = undefined;

	export let checked: boolean = defaultChecked;
	export let validateBeforeChange: (e: MouseEvent) => boolean = () => true;

	function toggle(e: MouseEvent) {
		if (validateBeforeChange(e) == false) return;
		checked = !checked;
		dispatch('checkedChange', { event: e, value: checked });
	}

	function preventEnter(event: KeyboardEvent) {
		if (event.key === 'Enter') event.preventDefault();
	}
</script>

<button
	on:click={toggle}
	on:keydown={preventEnter}
	{id}
	{disabled}
	aria-checked={checked}
	type="button"
	role="checkbox"
	title="Switch to {checked ? 'chat' : 'table'} mode"
	value="on"
	class={cn(
		'peer relative flex items-center justify-center gap-[7px] sm:gap-[11px] h-8 sm:h-9 w-[64px] sm:w-[72px] shrink-0 rounded-full bg-[#F2F4F7] data-dark:bg-[#282C34] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed  aria-checked:border-[#4169e1] data-dark:aria-checked:border-[#5b7ee5] overflow-hidden',
		className
	)}
>
	<svg width="22" height="23" viewBox="0 0 17 18" fill="none" xmlns="http://www.w3.org/2000/svg">
		<path
			fill-rule="evenodd"
			clip-rule="evenodd"
			d="M4.57143 4C3.97969 4 3.5 4.47969 3.5 5.07143V6.05357H8.5H13.5V5.07143C13.5 4.47969 13.0203 4 12.4286 4H4.57143ZM3.5 9.98206V6.94643H8.05357V9.98206H3.5ZM3.5 10.8749V12.9286C3.5 13.5203 3.97969 14 4.57143 14H8.05357V10.8749H3.5ZM8.94643 10.8749V14H12.4286C13.0203 14 13.5 13.5203 13.5 12.9286V10.8749H8.94643ZM13.5 9.98206V6.94643H8.94643V9.98206H13.5Z"
			fill="#667085"
		/>
	</svg>

	<MultiturnChatIcon class="h-6 text-[#98A2B3]" />

	<div
		class="absolute top-1/2 -translate-y-1/2 left-0 flex items-center justify-center h-6 sm:h-7 aspect-square bg-white rounded-full transition-transform {checked
			? 'translate-x-1'
			: 'translate-x-[36px] sm:translate-x-[40px]'}"
	>
		<div class="relative">
			<MultiturnChatIcon
				class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-6 transition-opacity {checked
					? 'opacity-0'
					: 'opacity-100'}"
			/>

			<svg
				width="22"
				height="23"
				viewBox="0 0 17 18"
				fill="none"
				xmlns="http://www.w3.org/2000/svg"
				class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 transition-opacity {checked
					? 'opacity-100'
					: 'opacity-0'}"
			>
				<path
					fill-rule="evenodd"
					clip-rule="evenodd"
					d="M4.57143 4C3.97969 4 3.5 4.47969 3.5 5.07143V6.05357H8.5H13.5V5.07143C13.5 4.47969 13.0203 4 12.4286 4H4.57143ZM3.5 9.98206V6.94643H8.05357V9.98206H3.5ZM3.5 10.8749V12.9286C3.5 13.5203 3.97969 14 4.57143 14H8.05357V10.8749H3.5ZM8.94643 10.8749V14H12.4286C13.0203 14 13.5 13.5203 13.5 12.9286V10.8749H8.94643ZM13.5 9.98206V6.94643H8.94643V9.98206H13.5Z"
					fill="black"
				/>
			</svg>
		</div>
	</div>
</button>
<input
	{disabled}
	{required}
	{name}
	bind:checked
	aria-hidden="true"
	tabindex="-1"
	type="checkbox"
	value="on"
	class="pointer-events-none absolute !m-0 h-4 w-4 opacity-0"
/>
