<script lang="ts">
	
	interface Props {
		class?: string | undefined | null;
		ascending?: boolean;
	}

	let { class: className = undefined, ascending = true }: Props = $props();
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
			d="M8.47656 9.00007L12.667 9"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 6.90527H11.0956"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 4.80957H10.048"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 11.0957H13.7147"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M5.59468 13.7147V4.28613M5.59468 13.7147C5.22789 13.7147 4.54262 12.6701 4.28516 12.4052M5.59468 13.7147C5.96147 13.7147 6.64674 12.6701 6.9042 12.4052"
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
			d="M8.47656 6.90527L12.667 6.90531"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 9H11.0956"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 11.0957H10.048"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M8.47656 4.80957H13.7147"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M5.59468 13.7147V4.28613M5.59468 13.7147C5.22789 13.7147 4.54262 12.6701 4.28516 12.4052M5.59468 13.7147C5.96147 13.7147 6.64674 12.6701 6.9042 12.4052"
			stroke="currentColor"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
