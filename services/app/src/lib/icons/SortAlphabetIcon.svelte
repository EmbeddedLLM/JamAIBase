<script lang="ts">
	let className: string | undefined | null = undefined;
	export { className as class };
	export let ascending = true;
</script>

{#if ascending}
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
		class={className}
	>
		<path
			d="M4.5 9.75H6.71055C7.1756 9.75 7.40812 9.75 7.47006 9.90005C7.532 10.0502 7.37378 10.2302 7.05733 10.5902L5.23846 12.6598C4.92201 13.0198 4.76379 13.1998 4.82573 13.3499C4.88767 13.5 5.12019 13.5 5.58524 13.5H7.5"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M4.5 6.75L5.55278 4.40264C5.74792 3.96755 5.84549 3.75 6 3.75C6.15451 3.75 6.25208 3.96755 6.44722 4.40264L7.5 6.75"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M12 12.75V4.5M12 12.75C11.5799 12.75 10.7949 11.7217 10.5 11.4609M12 12.75C12.4201 12.75 13.2051 11.7217 13.5 11.4609"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{:else}
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
		class={className}
	>
		<path
			d="M4.5 3.75H6.71055C7.1756 3.75 7.40812 3.75 7.47006 3.90005C7.532 4.05016 7.37378 4.23016 7.05733 4.59021L5.23846 6.65979C4.92201 7.01984 4.76379 7.19984 4.82573 7.34995C4.88767 7.5 5.12019 7.5 5.58524 7.5H7.5"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M4.5 13.9287L5.55278 11.5813C5.74792 11.1463 5.84549 10.9287 6 10.9287C6.15451 10.9287 6.25208 11.1463 6.44722 11.5813L7.5 13.9287"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M12 12.75V4.5M12 12.75C11.5799 12.75 10.7949 11.7217 10.5 11.4609M12 12.75C12.4201 12.75 13.2051 11.7217 13.5 11.4609"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
