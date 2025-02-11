<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import { activeProject, showLoadingOverlay } from '$globalStore';
	import { textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';

	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';

	async function handleExportProject(projectId?: string) {
		if (!confirm(`Export project ${$activeProject?.name ?? $page.params.project_id ?? projectId}?`))
			return;
		if (PUBLIC_IS_LOCAL === 'false') {
			window
				.open(
					`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${projectId ?? $page.params.project_id}/export`,
					'_blank'
				)
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${projectId ?? $page.params.project_id}/export`
			);

			if (response.ok) {
				const contentDisposition = response.headers.get('content-disposition');
				const responseBody = await response.blob();
				textToFileDownload(
					/filename="(?<filename>.*)"/.exec(contentDisposition ?? '')?.groups?.filename ||
						`${$activeProject?.id}.parquet`,
					responseBody
				);
			} else {
				const responseBody = await response.json();
				logger.error(`PROJECT_EXPORT_PROJECT`, responseBody);
				console.error(responseBody);
				toast.error('Failed to export project', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}

			$showLoadingOverlay = false;
		}
	}
</script>

<slot {handleExportProject} />
