<script lang="ts">
	import { fade } from 'svelte/transition';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import * as Dialog from './index.js';
	import { cn } from '$lib/utils.js';

	type $$Props = DialogPrimitive.ContentProps & {
		overlayClass?: string;
	};

	let className: $$Props['class'] = undefined;
	export let overlayClass: string = '';
	export let transition: $$Props['transition'] = fade;
	export let transitionConfig: $$Props['transitionConfig'] = {
		duration: 100
	};
	export { className as class };
</script>

<Dialog.Portal>
	<Dialog.Overlay class={overlayClass} />
	<DialogPrimitive.Content
		{transition}
		{transitionConfig}
		class={cn(
			'fixed left-[50%] top-[50%] z-50 flex flex-col w-full max-w-lg translate-x-[-50%] translate-y-[-50%] bg-white data-dark:bg-[#303338] shadow-lg rounded-xl focus-visible:outline-none',
			className
		)}
		{...$$restProps}
	>
		<slot />
	</DialogPrimitive.Content>
</Dialog.Portal>
