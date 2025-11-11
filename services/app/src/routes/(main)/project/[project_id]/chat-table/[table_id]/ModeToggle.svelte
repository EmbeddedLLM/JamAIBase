<script lang="ts">
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import { cn } from '$lib/utils';
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher<{
		checkedChange: { event: MouseEvent; value: boolean };
	}>();

	interface Props {
		class?: string | undefined | null;
		id?: string | undefined;
		defaultChecked?: boolean;
		disabled?: boolean | undefined;
		required?: boolean | undefined;
		name?: string | undefined;
		checked?: boolean;
		validateBeforeChange?: (e: MouseEvent) => boolean;
	}

	let {
		class: className = undefined,
		id = undefined,
		defaultChecked = false,
		disabled = undefined,
		required = undefined,
		name = undefined,
		checked = $bindable(defaultChecked),
		validateBeforeChange = () => true
	}: Props = $props();

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
	onclick={toggle}
	onkeydown={preventEnter}
	{id}
	{disabled}
	aria-checked={checked}
	type="button"
	role="checkbox"
	title="Switch to {checked ? 'chat' : 'table'} mode"
	value="on"
	class={cn(
		'peer relative flex h-8 w-[64px] shrink-0 items-center justify-center gap-[7px] overflow-hidden rounded-full bg-[#E4E7EC] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed aria-checked:border-[#4169e1] data-dark:bg-[#282C34] data-dark:aria-checked:border-[#5b7ee5]  sm:h-9 sm:w-[72px] sm:gap-[11px]',
		className
	)}
>
	<svg width="22" height="23" viewBox="0 0 17 17" fill="none" xmlns="http://www.w3.org/2000/svg">
		<path
			d="M12.3077 4H4.69231C4.30996 4 4 4.30996 4 4.69231V12.3077C4 12.6901 4.30996 13 4.69231 13H12.3077C12.6901 13 13 12.6901 13 12.3077V4.69231C13 4.30996 12.6901 4 12.3077 4Z"
			stroke="#98A2B3"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path d="M4 6.07715H13" stroke="#98A2B3" stroke-linecap="round" stroke-linejoin="round" />
		<path
			d="M8.5 6.07715V13.0002"
			stroke="#98A2B3"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path d="M4 9.53809H13" stroke="#98A2B3" stroke-linecap="round" stroke-linejoin="round" />
	</svg>

	<MultiturnChatIcon class="h-6 text-[#98A2B3]" />

	<div
		class="absolute left-0 top-1/2 flex aspect-square h-6 -translate-y-1/2 items-center justify-center rounded-full bg-white transition-transform sm:h-7 {checked
			? 'translate-x-1'
			: 'translate-x-[36px] sm:translate-x-[40px]'}"
	>
		<div class="relative text-[#667085]">
			<MultiturnChatIcon
				filled
				class="absolute left-1/2 top-1/2 h-6 -translate-x-1/2 -translate-y-1/2 transition-opacity {checked
					? 'opacity-0'
					: 'opacity-100'}"
			/>

			<svg
				width="22"
				height="23"
				viewBox="0 0 17 18"
				fill="none"
				xmlns="http://www.w3.org/2000/svg"
				class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 transition-opacity {checked
					? 'opacity-100'
					: 'opacity-0'}"
			>
				<path
					fill-rule="evenodd"
					clip-rule="evenodd"
					d="M4.57143 4C3.97969 4 3.5 4.47969 3.5 5.07143V6.05357H8.5H13.5V5.07143C13.5 4.47969 13.0203 4 12.4286 4H4.57143ZM3.5 9.98206V6.94643H8.05357V9.98206H3.5ZM3.5 10.8749V12.9286C3.5 13.5203 3.97969 14 4.57143 14H8.05357V10.8749H3.5ZM8.94643 10.8749V14H12.4286C13.0203 14 13.5 13.5203 13.5 12.9286V10.8749H8.94643ZM13.5 9.98206V6.94643H8.94643V9.98206H13.5Z"
					fill="currentColor"
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
