<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { MediaQuery } from 'svelte/reactivity';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import axios, { CanceledError } from 'axios';
	import {
		showDock,
		showLoadingOverlay,
		uploadQueue,
		uploadController,
		modelsAvailable,
		activeOrganization,
		showRightDock
	} from '$globalStore';
	import logger from '$lib/logger';
	import type { UploadQueue } from '$lib/types';

	import SideDock from './SideDock.svelte';
	import UploadTab from './UploadTab.svelte';
	import ChatSideDock from './ChatSideDock.svelte';
	import BreadcrumbsBar from './BreadcrumbsBar.svelte';
	import UserDetailsBtn from '$lib/components/preset/UserDetailsBtn.svelte';
	import { setTableRowsState, setTableState } from '$lib/components/tables/tablesState.svelte';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SideBarIcon from '$lib/icons/SideBarIcon.svelte';

	setTableState();
	setTableRowsState();

	let { data, children } = $props();
	let { organizationData } = $derived(data);

	const bigScreen = new MediaQuery('min-width: 768px');

	let completedUploads: UploadQueue['queue'] = $state([]);
	let isUploadingFiles = false;

	const uploadFiles = async () => {
		if ($uploadQueue.activeFile) return;

		isUploadingFiles = true;

		while ($uploadQueue.queue.length !== 0) {
			const fileToUpload = $uploadQueue.queue[0];
			$uploadQueue = {
				activeFile: fileToUpload,
				progress: 0,
				queue: $uploadQueue.queue.slice(1)
			};

			try {
				$uploadController = new AbortController();

				const uploadRes = await axios({
					...fileToUpload.request,
					onUploadProgress: (progressEvent) => {
						if (!progressEvent.total) return;
						const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
						$uploadQueue.progress = percentCompleted;
					},
					signal: $uploadController.signal
				});

				if (uploadRes.status != 200) {
					logger.error('FILE_UPLOAD_FAILED', {
						file: fileToUpload.file.name,
						response: uploadRes.data
					});
					alert(
						'Failed to upload file: ' +
							(uploadRes.data.message || JSON.stringify(uploadRes.data)) +
							`\nRequest ID: ${uploadRes.data.request_id}`
					);
				} else {
					completedUploads = [...completedUploads, fileToUpload];
					fileToUpload.invalidate?.();

					if (uploadRes.data.err_message) {
						alert(
							'Error while uploading file: ' + uploadRes.data.message ||
								JSON.stringify(uploadRes.data) + `\nRequest ID: ${uploadRes.data.request_id}`
						);
					}
				}
			} catch (err) {
				if (!(err instanceof CanceledError && err.code == 'ERR_CANCELED')) {
					//@ts-expect-error AxiosError
					logger.error('FILE_UPLOAD_FAILED', err?.response?.data);
					alert(
						'Failed to upload file: ' +
							//@ts-expect-error AxiosError
							(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
							//@ts-expect-error AxiosError
							`\nRequest ID: ${err?.response?.data?.request_id}`
					);
				}
			}

			$uploadQueue = {
				...$uploadQueue,
				activeFile: null,
				progress: 0
			};
		}
	};

	afterNavigate((navigation) => {
		if ($modelsAvailable.length === 0 && $activeOrganization && page.params.project_id) {
			fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/organizations/models/catalogue?${new URLSearchParams([['organization_id', $activeOrganization.id]])}`,
				{
					credentials: 'same-origin',
					headers: {
						'x-project-id': page.params.project_id
					}
				}
			)
				.then((res) => Promise.all([res, res.json()]))
				.then(([response, responseBody]) => {
					if (response.ok) {
						$modelsAvailable = responseBody.items;
					} else {
						logger.error('MODELS_FETCH_FAILED', responseBody);
						console.error(responseBody);
					}
				});
		}

		if (
			navigation.to?.url.pathname.startsWith('/chat') &&
			!navigation.from?.url.pathname.startsWith('/chat')
		) {
			$showDock = true;
		}
	});
	$effect(() => {
		$uploadQueue;
		uploadFiles();
	});

	let animationId: ReturnType<typeof requestAnimationFrame>;
	function handleResize() {
		if (animationId) {
			cancelAnimationFrame(animationId);
		}

		animationId = requestAnimationFrame(() => {
			if (bigScreen.current && page.url.pathname.startsWith('/chat')) {
				$showDock = true;
			}
		});
	}
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'c') $showRightDock = !$showRightDock;
	}}
	onresize={handleResize}
/>

<main class="flex h-screen flex-col">
	<div
		class="grid {$showDock
			? 'grid-cols-[minmax(0,_auto)] md:grid-cols-[15.5rem,_minmax(0,_auto)]'
			: 'grid-cols-[minmax(0,_auto)] md:grid-cols-[4.25rem,_minmax(0,_auto)]'} box-border h-screen bg-[#F2F4F7] transition-[grid-template-columns] duration-300 data-dark:bg-[#1E2024]"
	>
		{#if page.url.pathname.startsWith('/chat')}
			<ChatSideDock />
		{:else}
			<SideDock {organizationData} />
		{/if}

		<div
			style="grid-template-columns: minmax(0, auto) {$showRightDock && page.data.rightDock
				? '18rem'
				: '0rem'}"
			class="grid !h-screen {page.data.rightDock
				? 'transition-[grid-template-columns] duration-300'
				: ''} overflow-hidden"
		>
			<div inert={!bigScreen.current && $showDock} class="flex !h-screen flex-col @container">
				<div class="relative flex items-center justify-start gap-2 md:justify-between">
					<Button
						variant="ghost"
						title="Show/hide side navigation bar"
						onclick={() => ($showDock = !$showDock)}
						class="group ml-3 mt-1.5 aspect-square h-12 w-12 flex-[0_0_auto] rounded-full p-0 duration-200 md:hidden"
					>
						<SideBarIcon class="scale-125" />
					</Button>

					{#if !page.data.hideBreadcrumbs}
						<BreadcrumbsBar />
					{/if}

					{#if !page.data.hideUserDetailsBtn}
						<UserDetailsBtn />
					{/if}
				</div>

				{@render children?.()}
			</div>

			{#if page.data.rightDock}
				<page.data.rightDock />
			{/if}
		</div>

		<UploadTab bind:completedUploads />
	</div>

	{#if $showLoadingOverlay}
		<div
			class="absolute bottom-0 left-0 right-0 top-0 z-[9999] flex items-center justify-center bg-black/60"
		>
			<LoadingSpinner class="h-6 w-6 text-[#5b7ee5]" />
		</div>
	{/if}
</main>
