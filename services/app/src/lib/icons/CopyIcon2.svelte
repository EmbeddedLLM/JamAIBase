<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
</script>

<svg viewBox="0 0 17 17" fill="none" xmlns="http://www.w3.org/2000/svg" class={className}>
	<path
		d="M6.42278 13.0002H12.3074C12.6898 13.0002 12.9997 12.6902 12.9997 12.3079V6.42326C12.9997 6.04091 12.6898 5.73096 12.3074 5.73096H6.42278C6.04042 5.73096 5.73047 6.04091 5.73047 6.42326V12.3079C5.73047 12.6902 6.04042 13.0002 6.42278 13.0002Z"
		stroke="#1D2939"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
	<path
		d="M4 10.9231V4.69231C4 4.50869 4.07294 4.33261 4.20277 4.20277C4.33261 4.07294 4.50869 4 4.69231 4H10.9231"
		stroke="#1D2939"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
