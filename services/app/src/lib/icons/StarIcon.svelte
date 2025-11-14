<script lang="ts">
	interface Props {
		class?: string | undefined | null;
	}

	let { class: className = undefined }: Props = $props();
	
</script>

<svg
	width="10"
	height="10"
	viewBox="0 0 10 10"
	fill="none"
	xmlns="http://www.w3.org/2000/svg"
	class={className}
>
	<path
		d="M1.2014 4.71247L3.77618 3.77618L4.71247 1.2014C4.81011 0.932868 5.18989 0.932867 5.28753 1.2014L6.22382 3.77618L8.79858 4.71247C9.06714 4.81011 9.06714 5.18989 8.79858 5.28753L6.22382 6.22382L5.28753 8.79858C5.18989 9.06714 4.81011 9.06714 4.71247 8.79858L3.77618 6.22382L1.2014 5.28753C0.932868 5.18989 0.932867 4.81011 1.2014 4.71247Z"
		stroke="currentColor"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
