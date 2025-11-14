<script lang="ts">
	import { Toaster as Sonner, type ToasterProps as SonnerProps } from 'svelte-sonner';
	import { preferredTheme } from '$globalStore';
	import { mode } from 'mode-watcher';

	let { ...restProps }: SonnerProps = $props();
</script>

<Sonner theme={$preferredTheme.toLowerCase() as 'light' | 'dark' | 'system'} {...restProps} />
