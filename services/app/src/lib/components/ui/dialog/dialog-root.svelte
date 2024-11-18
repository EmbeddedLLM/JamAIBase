<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	type $$Props = DialogPrimitive.Props;

	export let open = false;
</script>

<DialogPrimitive.Root
	onOutsideClick={(e) => {
		if (
			//@ts-ignore
			document.getElementById('upload-tab-global')?.contains(e.target) ||
			//@ts-ignore
			document.querySelector('[data-sonner-toaster]')?.contains(e.target)
		)
			e.preventDefault();
	}}
	bind:open
	{...$$restProps}
>
	<slot />
</DialogPrimitive.Root>
