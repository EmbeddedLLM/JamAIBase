<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg width="22" height="22" xmlns="http://www.w3.org/2000/svg" class={className}>
	<path
		d="m5.27,5.19l3.1,0l0,14.81l-3.1,0a0.77,1.48 0 0 1 -0.77,-1.48l0,-11.85a0.77,1.48 0 0 1 0.77,-1.48z"
		fill="#475467"
		transform="scale(1 0.875)"
		class="opacity-0 group-hover:opacity-100 transition-opacity"
	/>
	<path
		d="m8.38,17.49l0,-12.99"
		fill="none"
		stroke="#475467"
		stroke-linecap="round"
		stroke-linejoin="round"
		stroke-width="1"
	/>
	<path
		d="m17.5,5.5l0,11c0,0.55 -0.45,1 -1,1l-11,0c-0.55,0 -1,-0.45 -1,-1l0,-11c0,-0.55 0.45,-1 1,-1l11,0c0.55,0 1,0.45 1,1z"
		fill="none"
		stroke="#475467"
		stroke-linecap="round"
		stroke-linejoin="round"
		stroke-width="1"
	/>
</svg>
