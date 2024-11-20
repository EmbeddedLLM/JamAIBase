<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import axios, { CanceledError } from 'axios';
	import {
		showDock,
		showLoadingOverlay,
		uploadQueue,
		uploadController,
		modelsAvailable,
		activeOrganization
	} from '$globalStore';
	import logger from '$lib/logger';
	import type { UploadQueue } from '$lib/types';

	import SideDock from './SideDock.svelte';
	import UploadTab from './UploadTab.svelte';
	import BreadcrumbsBar from './BreadcrumbsBar.svelte';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SideBarIcon from '$lib/icons/SideBarIcon.svelte';

	export let data;
	$: ({ organizationData, userData } = data);

	let windowWidth: number;

	let completedUploads: UploadQueue['queue'] = [];
	let isUploadingFiles = false;
	$: $uploadQueue, uploadFiles();

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

	afterNavigate(() => {
		if ($modelsAvailable.length === 0 && $activeOrganization && $page.params.project_id) {
			fetch(`${PUBLIC_JAMAI_URL}/api/v1/models`, {
				credentials: 'same-origin',
				headers: {
					'x-project-id': $page.params.project_id
				}
			})
				.then((res) => Promise.all([res, res.json()]))
				.then(([response, responseBody]) => {
					if (response.ok) {
						$modelsAvailable = responseBody.data;
					} else {
						logger.error('MODELS_FETCH_FAILED', responseBody);
						console.error(responseBody);
					}
				});
		}
	});
</script>

<svelte:window bind:innerWidth={windowWidth} />

<main class="flex flex-col h-screen">
	<div
		class="grid {$showDock
			? 'grid-cols-[minmax(0,_auto)] md:grid-cols-[15.5rem,_minmax(0,_auto)]'
			: 'grid-cols-[minmax(0,_auto)] md:grid-cols-[3.5rem,_minmax(0,_auto)]'} h-screen box-border bg-[#F9FAFB] data-dark:bg-[#1E2024] transition-[grid-template-columns] duration-300"
	>
		<SideDock {organizationData} />

		<div
			inert={windowWidth !== undefined && windowWidth < 768 && $showDock}
			class="@container flex flex-col !h-screen"
		>
			<div class="flex items-center">
				<Button
					variant="ghost"
					title="Show/hide side navigation bar"
					on:click={() => ($showDock = !$showDock)}
					class="flex-[0_0_auto] md:hidden mt-1.5 ml-3 p-0 h-12 w-12 aspect-square rounded-full duration-200 group"
				>
					<SideBarIcon class="scale-125" />
				</Button>

				{#if !$page.data.hideBreadcrumbs}
					<BreadcrumbsBar />
				{/if}
			</div>

			<slot />
		</div>

		<UploadTab bind:completedUploads />
	</div>

	{#if $showLoadingOverlay}
		<div
			class="absolute top-0 bottom-0 left-0 right-0 z-[9999] flex items-center justify-center bg-black/60"
		>
			<LoadingSpinner class="h-6 w-6 text-[#5b7ee5]" />
		</div>
	{/if}
</main>
