<script lang="ts">
	let className: string | undefined | null = undefined;
	export { className as class };

	export let placeholder: string | undefined = undefined;
	export let id: string | undefined = undefined;
	export let disabled: boolean = false;
	export let value: string | number = '';
</script>

<div class="flex flex-col">
	<input {...$$restProps} {placeholder} {disabled} {id} bind:value type="range" class={className} />

	{#if $$restProps.min && $$restProps.max}
		<div class="flex justify-between text-xs text-gray-400">
			<span>{$$restProps.min}</span>
			<span>{$$restProps.max}</span>
		</div>
	{/if}
</div>

<style>
	input[type='range'] {
		height: 21px;
		-webkit-appearance: none;
		appearance: none;
		margin: 4px 0;
		width: 100%;
		background: transparent;
	}
	input[type='range']:focus {
		outline: none;
	}
	input[type='range']::-webkit-slider-runnable-track {
		width: 100%;
		height: 6px;
		cursor: pointer;
		/* animate: 0.2s; */
		box-shadow: 0px 0px 1px #000000;
		background: #5b7ee5;
		border-radius: 50px;
		border: 0px solid #000000;
	}
	input[type='range']::-webkit-slider-thumb {
		box-shadow: 1px 1px 3px #000000;
		border: 0px solid #000000;
		height: 14px;
		width: 14px;
		border-radius: 50px;
		background: #4169e1;
		cursor: pointer;
		-webkit-appearance: none;
		margin-top: -4px;
	}
	input[type='range']:focus::-webkit-slider-runnable-track {
		background: #5b7ee5;
	}
	input[type='range']::-moz-range-track {
		width: 100%;
		height: 6px;
		cursor: pointer;
		/* animate: 0.2s; */
		box-shadow: 0px 0px 1px #000000;
		background: #5b7ee5;
		border-radius: 50px;
		border: 0px solid #000000;
	}
	input[type='range']::-moz-range-thumb {
		box-shadow: 1px 1px 3px #000000;
		border: 0px solid #000000;
		height: 14px;
		width: 14px;
		border-radius: 50px;
		background: #4169e1;
		cursor: pointer;
	}
	input[type='range']::-ms-track {
		width: 100%;
		height: 6px;
		cursor: pointer;
		/* animate: 0.2s; */
		background: transparent;
		border-color: transparent;
		color: transparent;
	}
	input[type='range']::-ms-fill-lower {
		background: #5b7ee5;
		border: 0px solid #000000;
		border-radius: 100px;
		box-shadow: 0px 0px 1px #000000;
	}
	input[type='range']::-ms-fill-upper {
		background: #5b7ee5;
		border: 0px;
		border-radius: 100px;
		box-shadow: 0px 0px 1px #000000;
	}
	input[type='range']::-ms-thumb {
		margin-top: 1px;
		box-shadow: 1px 1px 3px #000000;
		border: 0px solid #000000;
		height: 14px;
		width: 14px;
		border-radius: 50px;
		background: #4169e1;
		cursor: pointer;
	}
	input[type='range']:focus::-ms-fill-lower {
		background: #5b7ee5;
	}
	input[type='range']:focus::-ms-fill-upper {
		background: #5b7ee5;
	}
</style>
