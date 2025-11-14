<script lang="ts">
	

	interface Props {
		class?: string | undefined | null;
		placeholder?: string | undefined;
		id?: string | undefined;
		disabled?: boolean;
		value?: string | number;
		[key: string]: any
	}

	let {
		class: className = undefined,
		placeholder = undefined,
		id = undefined,
		disabled = false,
		value = $bindable(''),
		...rest
	}: Props = $props();
</script>

<div class="flex flex-col">
	<input {...rest} {placeholder} {disabled} {id} bind:value type="range" class={className} />

	{#if rest.min && rest.max}
		<div class="flex justify-between text-xs text-gray-400">
			<span>{rest.min}</span>
			<span>{rest.max}</span>
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
		background: #d5607c;
		border-radius: 50px;
		border: 0px solid #000000;
	}
	input[type='range']::-webkit-slider-thumb {
		box-shadow: 1px 1px 3px #000000;
		border: 0px solid #000000;
		height: 14px;
		width: 14px;
		border-radius: 50px;
		background: #a62050;
		cursor: pointer;
		-webkit-appearance: none;
		margin-top: -4px;
	}
	input[type='range']:focus::-webkit-slider-runnable-track {
		background: #d5607c;
	}
	input[type='range']::-moz-range-track {
		width: 100%;
		height: 6px;
		cursor: pointer;
		/* animate: 0.2s; */
		box-shadow: 0px 0px 1px #000000;
		background: #d5607c;
		border-radius: 50px;
		border: 0px solid #000000;
	}
	input[type='range']::-moz-range-thumb {
		box-shadow: 1px 1px 3px #000000;
		border: 0px solid #000000;
		height: 14px;
		width: 14px;
		border-radius: 50px;
		background: #a62050;
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
		background: #d5607c;
		border: 0px solid #000000;
		border-radius: 100px;
		box-shadow: 0px 0px 1px #000000;
	}
	input[type='range']::-ms-fill-upper {
		background: #d5607c;
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
		background: #a62050;
		cursor: pointer;
	}
	input[type='range']:focus::-ms-fill-lower {
		background: #d5607c;
	}
	input[type='range']:focus::-ms-fill-upper {
		background: #d5607c;
	}
</style>
