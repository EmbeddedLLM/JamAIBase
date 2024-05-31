<script lang="ts">
	import { cn } from '$lib/utils';
	import { createEventDispatcher } from 'svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

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
	value="on"
	class={cn(
		'peer h-4 w-4 shrink-0 rounded-sm border border-[#4169e1] data-dark:border-[#5b7ee5] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:border-neutral-500 aria-checked:bg-[#4169e1] data-dark:checked:bg-[#5b7ee5] aria-checked:text-white aria-checked:border-[#4169e1] data-dark:aria-checked:border-[#5b7ee5] overflow-hidden',
		className
	)}
>
	<CheckIcon
		class={`h-4 w-4 pointer-events-none ${
			checked ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-75 translate-y-1'
		} transition-[opacity,transform]`}
	/>
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
