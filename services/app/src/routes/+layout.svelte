<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { beforeNavigate, afterNavigate } from '$app/navigation';
	import NProgress from 'nprogress';
	import '../app.css';
	import 'overlayscrollbars/overlayscrollbars.css';
	import '@fontsource/roboto';
	import { showDock, showRightDock, preferredTheme, activeOrganization } from '$globalStore';

	let timeout: NodeJS.Timeout;
	NProgress.configure({ showSpinner: false });
	beforeNavigate(() => (timeout = setTimeout(() => NProgress.start(), 250)));
	afterNavigate(() => {
		clearTimeout(timeout);
		NProgress.done();
	});

	export let data;
	$: ({ dockOpen, rightDockOpen, userData, activeOrganizationId } = data);

	//* Initialize showDock using cookie store
	$: $showDock = dockOpen;
	$: $showRightDock = rightDockOpen;

	$: if (browser) {
		document.cookie = `dockOpen=${$showDock}; path=/; sameSite=Lax`;
		document.cookie = `rightDockOpen=${$showRightDock}; path=/; sameSite=Lax`;
	}

	$: if (browser) {
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

	$: if (activeOrganizationId) {
		$activeOrganization =
			userData?.organizations?.find((org) => org.organization_id === activeOrganizationId) ?? null;
	}
	$: if (browser && $activeOrganization) {
		document.cookie = `activeOrganizationId=${$activeOrganization?.organization_id}; path=/; max-age=3153600000; samesite=strict`;
	}

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
</script>

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

<slot />

<style>
	:global(body) {
		font-family: 'Roboto', sans-serif;
	}
</style>
