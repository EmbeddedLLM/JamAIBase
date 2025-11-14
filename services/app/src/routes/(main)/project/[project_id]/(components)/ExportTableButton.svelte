<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/state';
	import { showLoadingOverlay } from '$globalStore';
	import { textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';

	import { CustomToastDesc, toast } from '$lib/components/ui/sonner';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableId: string | undefined;
		children?: import('svelte').Snippet<[any]>;
	}

	let { tableType, tableId, children }: Props = $props();

	async function handleExportTable() {
		if (!tableId || $showLoadingOverlay) return;
		if (!confirm(`Export table ${tableId}?`)) return;

		if (page.data.ossMode) {
			window
				.open(
					`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/export?${new URLSearchParams([['table_id', tableId]])}`,
					'_blank'
				)
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/export?${new URLSearchParams([['table_id', tableId]])}`,
				{
					headers: {
						'x-project-id': page.params.project_id
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

{@render children?.({ handleExportTable })}
