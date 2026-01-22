<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { page } from '$app/state';
	import { activeProject, showLoadingOverlay } from '$globalStore';
	import { textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';

	import { m } from '$lib/paraglide/messages';
	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	interface Props {
		children?: import('svelte').Snippet<[{ handleExportProject: typeof handleExportProject }]>;
	}

	let { children }: Props = $props();

	async function handleExportProject(projectId?: string) {
		if (
			!confirm(
				m.project_export_confirm({
					project_name: $activeProject?.name ?? page.params.project_id ?? projectId ?? ''
				})
			)
		)
			return;
		if (page.data.ossMode) {
			window
				.open(
					`${PUBLIC_JAMAI_URL}/api/owl/projects/export?${new URLSearchParams([['project_id', projectId ?? page.params.project_id ?? '']])}`,
					'_blank'
				)
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/projects/export?${new URLSearchParams([['project_id', projectId ?? page.params.project_id ?? '']])}`
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
				toast.error(m.project_export_fail(), {
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

{@render children?.({ handleExportProject })}
