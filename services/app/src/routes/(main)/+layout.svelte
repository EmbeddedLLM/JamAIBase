<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount } from 'svelte';
	import axios, { CanceledError } from 'axios';
	import {
		showDock,
		showLoadingOverlay,
		uploadQueue,
		uploadController,
		modelsAvailable
	} from '$globalStore';
	import logger from '$lib/logger';
	import type { UploadQueue } from '$lib/types';

	import SideDock from './SideDock.svelte';
	import UploadTab from './UploadTab.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';

	export let data;
	$: ({ organizationData } = data);

	let windowWidth: number;

	let completedUploads: UploadQueue['queue'] = [];
	let isUploadingFiles = false;
	$: uploadFiles($uploadQueue);

	const uploadFiles = async (queue: typeof $uploadQueue) => {
		if ($uploadQueue.activeFile) return;

		isUploadingFiles = true;

		while ($uploadQueue.queue.length !== 0) {
			const fileToUpload = $uploadQueue.queue[0];
			$uploadQueue.activeFile = fileToUpload.file;
			$uploadQueue.progress = 0;
			$uploadQueue.queue = $uploadQueue.queue.filter(
				(file) => file.file.name != fileToUpload.file.name
			);
			$uploadQueue = $uploadQueue;

			const formData = new FormData();
			formData.append('file', fileToUpload.file);
			formData.append('file_name', fileToUpload.file.name);
			if (fileToUpload.table_id) formData.append('table_id', fileToUpload.table_id);

			try {
				$uploadController = new AbortController();

				const uploadres = await axios.post(
					`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/upload_file`,
					formData,
					{
						headers: {
							'Content-Type': 'multipart/form-data',
							'x-project-id': fileToUpload.project_id
						},
						withCredentials: true,
						onUploadProgress: (progressEvent) => {
							if (!progressEvent.total) return;
							const percentCompleted = Math.round(
								(progressEvent.loaded * 100) / progressEvent.total
							);
							$uploadQueue.progress = percentCompleted;
						},
						signal: $uploadController.signal
					}
				);

				if (uploadres.status != 200) {
					logger.error('FILE_UPLOAD_FAILED', {
						file: fileToUpload.file.name,
						response: uploadres.data
					});
					alert(
						'Failed to upload file: ' + (uploadres.data.message || JSON.stringify(uploadres.data))
					);
				} else {
					completedUploads = [...completedUploads, fileToUpload];
					fileToUpload.invalidate?.();

					if (uploadres.data.err_message) {
						alert(
							'Error while uploading file: ' + uploadres.data.message ||
								JSON.stringify(uploadres.data)
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
							(err?.response?.data.message || JSON.stringify(err?.response?.data))
					);
				}
			}

			$uploadQueue.activeFile = null;
			$uploadQueue.progress = 0;
			$uploadQueue = $uploadQueue;
		}
	};

	onMount(() => {
		fetch(`${PUBLIC_JAMAI_URL}/api/v1/models`, {
			method: 'GET',
			credentials: 'same-origin'
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
	});
</script>

<svelte:window bind:innerWidth={windowWidth} />

<main class="flex flex-col h-screen">
	<div
		class={`grid ${
			$showDock ? 'grid-cols-[15.5rem,_minmax(0,_auto)]' : 'grid-cols-[4.2rem,_minmax(0,_auto)]'
		} h-screen box-border bg-[#F9FAFB] data-dark:bg-[#1E2024] transition-[grid-template-columns] duration-300`}
	>
		<SideDock {organizationData} />

		<slot />

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
