<script lang="ts">
	import { env } from '$env/dynamic/public';
	import axios, { CanceledError } from 'axios';
	import { showDock, showLoadingOverlay, uploadQueue, uploadController } from '$globalStore';
	import logger from '$lib/logger';
	import type { UploadQueue } from '$lib/types';

	import SideDock from './SideDock.svelte';
	import UploadTab from './UploadTab.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let data;
	$: ({ organizationData, userData } = data);

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
							'Content-Type': 'multipart/form-data'
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
</script>

<svelte:window bind:innerWidth={windowWidth} />

<main class="flex flex-col h-screen">
	<div
		class={`grid ${
			$showDock ? 'grid-cols-[15.5rem,_minmax(0,_auto)]' : 'grid-cols-[4.2rem,_minmax(0,_auto)]'
		} h-screen box-border bg-[#F7F8FC] data-dark:bg-[#1E2024] transition-[grid-template-columns] duration-300`}
	>
		<SideDock {organizationData} />

		<slot />

		<UploadTab bind:completedUploads />
	</div>

	{#if $showLoadingOverlay}
		<!-- TODO: Add loading spinner -->
	{/if}
</main>
