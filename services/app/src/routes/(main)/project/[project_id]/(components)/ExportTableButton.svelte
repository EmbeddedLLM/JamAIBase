<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/stores';
	import { showLoadingOverlay } from '$globalStore';
	import { textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';

	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableId: string | undefined;

	async function handleExportTable() {
		if (!tableId || $showLoadingOverlay) return;
		if (!confirm(`Export table ${tableId}?`)) return;

		if (PUBLIC_IS_LOCAL === 'false') {
			window
				.open(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableId}/export`, '_blank')
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableId}/export`,
				{
					headers: {
						'x-project-id': $page.params.project_id
					}
				}
			);

			if (response.ok) {
				const contentDisposition = response.headers.get('content-disposition');
				const responseBody = await response.blob();
				textToFileDownload(
					/filename="(?<filename>.*)"/.exec(contentDisposition ?? '')?.groups?.filename ||
						`${tableId}.parquet`,
					responseBody
				);
			} else {
				const responseBody = await response.json();
				logger.error(toUpper(`${tableType}TBL_TBL_EXPORTTBL`), responseBody);
				console.error(responseBody);
				toast.error('Failed to export rows', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc,
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

<slot {handleExportTable} />
