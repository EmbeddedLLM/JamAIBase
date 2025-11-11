<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { beforeNavigate, afterNavigate } from '$app/navigation';
	import NProgress from 'nprogress';
	import '../app.css';
	import 'overlayscrollbars/overlayscrollbars.css';
	import '@fontsource-variable/roboto-flex';
	import { showDock, showRightDock, preferredTheme, activeOrganization } from '$globalStore';

	import * as Tooltip from '$lib/components/ui/tooltip';
	import { CustomToastDesc, toast, Toaster } from '$lib/components/ui/sonner';

	let timeout: NodeJS.Timeout;
	NProgress.configure({ showSpinner: false });
	// beforeNavigate(() => (timeout = setTimeout(() => NProgress.start(), 250)));
	// afterNavigate(() => {
	// 	clearTimeout(timeout);
	// 	NProgress.done();
	// });

	let { data, children } = $props();
	let { dockOpen, rightDockOpen, user, activeOrganizationId } = $derived(data);

	//* Initialize showDock using cookie store
	// svelte-ignore state_referenced_locally (mimic run function)
	$showDock = dockOpen;
	$effect.pre(() => {
		$showDock = dockOpen;
	});
	// svelte-ignore state_referenced_locally (mimic run function)
	$showRightDock = rightDockOpen;
	$effect.pre(() => {
		$showRightDock = rightDockOpen;
	});

	$effect(() => {
		if (browser) {
			document.cookie = `dockOpen=${$showDock}; path=/; sameSite=Lax`;
			document.cookie = `rightDockOpen=${$showRightDock}; path=/; sameSite=Lax`;
		}
	});

	$effect(() => {
		if (browser) {
			if ($preferredTheme == 'SYSTEM') {
				document.documentElement.setAttribute(
					'data-theme',
					window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
				);
			} else {
				document.documentElement.setAttribute(
					'data-theme',
					$preferredTheme == 'LIGHT' ? 'light' : 'dark'
				);
			}
		}
	});

	$effect(() => {
		if (activeOrganizationId) {
			$activeOrganization =
				user?.organizations?.find((org) => org.id === activeOrganizationId) ?? null;
		}
	});
	// $effect(() => {
	// 	if (browser && $activeOrganization) {
	// 		document.cookie = `activeOrganizationId=${$activeOrganization?.id}; path=/; max-age=604800; samesite=strict`;
	// 	}
	// });

	onMount(() => {
		//* Reflect changes to user preference for immediately
		window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
			if ($preferredTheme == 'SYSTEM') {
				if (event.matches) {
					document.documentElement.setAttribute('data-theme', 'dark');
				} else {
					document.documentElement.setAttribute('data-theme', 'light');
				}
			}
		});
	});

	// function switchTheme(e: KeyboardEvent) {
	// 	const target = e.target as HTMLElement;
	// 	if (
	// 		target.tagName == 'INPUT' ||
	// 		target.tagName == 'TEXTAREA' ||
	// 		target.getAttribute('contenteditable') == 'true'
	// 	)
	// 		return;

	// 	const switchTheme = () => {
	// 		$preferredTheme = $preferredTheme == 'LIGHT' ? 'DARK' : 'LIGHT';
	// 	};

	// 	if (!e.ctrlKey && !e.shiftKey && !e.metaKey && e.key == 'c') {
	// 		//@ts-ignore
	// 		if (!document.startViewTransition) switchTheme();
	// 		//@ts-ignore
	// 		document.startViewTransition(switchTheme);
	// 	}
	// }

	// function switchTheme(e: KeyboardEvent) {
	// 	const target = e.target as HTMLElement;
	// 	if (
	// 		target.tagName == 'INPUT' ||
	// 		target.tagName == 'TEXTAREA' ||
	// 		target.getAttribute('contenteditable') == 'true'
	// 	)
	// 		return;

	// 	if (!e.ctrlKey && !e.shiftKey && !e.metaKey) {
	// 		switch (e.key) {
	// 			case 'e':
	// 				toast.error('Test', {
	// 					duration: Number.POSITIVE_INFINITY,
	// 					description: CustomToastDesc as any,
	// 					componentProps: {
	// 						description: 'Error desc here',
	// 						requestID: 'Request ID here'
	// 					}
	// 				});
	// 				break;
	// 			case 's':
	// 				toast.success('Test', {
	// 					duration: Number.POSITIVE_INFINITY,
	// 					description: CustomToastDesc as any,
	// 					componentProps: {
	// 						description: 'Error desc here',
	// 						requestID: 'Request ID here'
	// 					}
	// 				});
	// 				break;
	// 			case 'i':
	// 				toast.info('Test', {
	// 					duration: Number.POSITIVE_INFINITY,
	// 					description: CustomToastDesc as any,
	// 					componentProps: {
	// 						description: 'Error desc here',
	// 						requestID: 'Request ID here'
	// 					}
	// 				});
	// 				break;
	// 			default:
	// 				break;
	// 		}
	// 	}
	// }
</script>

<!-- <svelte:window on:keydown={switchTheme} /> -->

<!-- <svelte:head>
	<script>
		(function () {
			let theme = localStorage.getItem('theme');
			if (theme) {
				//* localStorage value for key `theme` is saved as "LIGHT" with double-quotes because of JSON serializer
				if (theme == '"SYSTEM"') {
					document.documentElement.setAttribute(
						'data-theme',
						window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
					);
				} else {
					document.documentElement.setAttribute(
						'data-theme',
						theme == '"LIGHT"' ? 'light' : 'dark'
					);
				}
			}
		})();
	</script>
</svelte:head> -->

<Toaster closeButton richColors />

<Tooltip.Provider>
	{@render children?.()}
</Tooltip.Provider>
