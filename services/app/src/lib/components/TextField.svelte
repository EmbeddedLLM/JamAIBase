<script lang="ts">
	import { cn } from '$lib/utils';

	export let showError: boolean = false;
	export let hideErrorCb: () => void = () => (showError = false);
	export let labelText: string;
	export let value: string | number = '';
	let className: string | undefined | null = undefined;
	export { className as class };
</script>

<div class={`relative flex flex-col ${showError && 'mb-5'} w-full`}>
	<span class="material-input-label">
		{labelText}
	</span>
	<!-- svelte-ignore a11y-autofocus -->
	<input
		placeholder=" "
		bind:value
		on:blur={hideErrorCb}
		{...$$restProps}
		class={cn(
			'material-input border-[#999] data-dark:border-[#454545] ',
			$$slots.trailing ? '!pr-12' : '',
			className
		)}
	/>

	{#if $$slots.trailing}
		<div class="absolute top-1/2 right-2 -translate-y-1/4">
			<slot name="trailing" />
		</div>
	{/if}

	{#if $$slots.errorText}
		<div class="absolute -bottom-5 left-0 text-xs pointer-events-none">
			<slot name="errorText" />
		</div>
	{/if}
</div>

<style>
	.material-input {
		@apply p-2;
		@apply px-0;
		@apply pt-6;
		@apply w-full;
		@apply bg-transparent;
		@apply outline-none;
		@apply border-b;
	}

	:has(.material-input):after {
		position: absolute;
		display: block;
		bottom: 0;
		left: 0;
		right: 0;
		content: '';
	}

	:has(.material-input):after {
		height: 2px;
		background: linear-gradient(to right, #4169e1, #ff6f61);
		z-index: 1;
		opacity: 0;
		transition: opacity 150ms cubic-bezier(0.4, 0, 0.2, 1);
	}

	:has(.material-input:focus):after {
		opacity: 1;
	}

	.material-input-label {
		@apply absolute;
		@apply top-1/2;
		@apply left-0;
		@apply -translate-y-1/4;
		@apply text-sm;
		@apply text-text/50;
		@apply pointer-events-none;
		@apply select-none;
		transition-property: transform, color, font-size, line-height;
		transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
		transition-duration: 150ms;
	}

	.material-input-label:has(+ .material-input:focus),
	.material-input-label:has(+ .material-input:not(:placeholder-shown)) {
		@apply text-xs;
		@apply -translate-y-[140%];
	}

	.material-input-label:has(+ .material-input:-webkit-autofill),
	.material-input-label:has(+ .material-input:-webkit-autofill:hover),
	.material-input-label:has(+ .material-input:-webkit-autofill:focus) {
		color: black;
	}

	.material-input:-webkit-autofill,
	.material-input:-webkit-autofill:hover,
	.material-input:-webkit-autofill:focus {
		border-width: 0 0 1px 0;
		-webkit-text-fill-color: rgb(38, 37, 2);
		-webkit-box-shadow: 0 0 0px 1000px #a8cef3 inset;
		box-shadow: 0 0 0px 1000px #a8cef3 inset;
		@apply rounded-md;
		/* @apply dark:[-webkit-box-shadow:0_0_0px_1000px_#253341_inset];
		@apply dark:[box-shadow:0_0_0px_1000px_#253341_inset]; */
		transition-property: background-color, border-color;
		transition-timing-function: ease-in-out;
		transition-duration: 150ms;
		color: white;
	}
</style>
