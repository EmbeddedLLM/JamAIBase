<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import xorWith from 'lodash/xorWith';
	import { v4 as uuidv4 } from 'uuid';
	import axios from 'axios';
	import Papa from 'papaparse';
	import Fuse from 'fuse.js';
	import { Trash2 } from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { showLoadingOverlay } from '$globalStore';
	import { extendArray, textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import ExportTableButton from './ExportTableButton.svelte';
	import { ColumnMatchDialog, DeleteTableDialog } from '../(dialogs)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';
	import FourCircles from '$lib/icons/FourCircles.svelte';

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	}

	let { tableType, tableData, refetchTable }: Props = $props();

	let isMatchingImportCols: {
		filename: string;
		rows: Record<string, string>[];
		cols: { id: string; name: string }[];
	} | null = $state(null);
	let isDeletingTable: string | null = $state(null);

	function handleImportTable() {
		if (!tableData) return;

		const fileInput = document.createElement('input');
		fileInput.type = 'file';
		fileInput.accept = '.csv';
		fileInput.onchange = (e) => {
			const file = (e.target as HTMLInputElement).files?.[0];
			if (!file) return;
			//@ts-ignore
			Papa.parse(file, {
				header: true,
				complete: (results) => {
					const filterFields = results.meta.fields?.filter(
						(field) => field !== 'ID' && field !== 'Updated at'
					);
					const filterTableCols = tableData?.cols
						.map((col) => col.id)
						.filter((field) => field !== 'ID' && field !== 'Updated at');

					const difference = xorWith(filterFields, filterTableCols);
					if (difference.length !== 0) {
						const sourceCols = extendArray(filterFields ?? [], filterTableCols?.length ?? 0).map(
							(col) => ({ id: uuidv4(), name: col })
						);
						const fuseSource = structuredClone(filterTableCols ?? []);
						const fuse = new Fuse(fuseSource, {
							threshold: 10,
							includeScore: true,
							shouldSort: true
						});

						let matchedSourceCols: {
							id: string;
							name: string;
							score: number;
						}[] = [];
						sourceCols.forEach((col) => {
							const res = fuse.search(col.name);
							if (res[0]?.refIndex !== undefined && !matchedSourceCols[res[0].refIndex]) {
								matchedSourceCols[res[0].refIndex] = { ...col, score: res[0]?.score ?? 0 };
							} else if (
								res[0]?.refIndex !== undefined &&
								matchedSourceCols[res[0].refIndex].score > (res[0].score ?? 1)
							) {
								let firstEmpty = matchedSourceCols.findIndex((v) => !v);
								firstEmpty = firstEmpty !== -1 ? firstEmpty : matchedSourceCols.length;
								matchedSourceCols[firstEmpty] = { ...col, score: res[0]?.score ?? 0 };
								[matchedSourceCols[firstEmpty], matchedSourceCols[res[0].refIndex]] = [
									matchedSourceCols[res[0].refIndex],
									matchedSourceCols[firstEmpty]
								];
							} else {
								let firstEmpty = matchedSourceCols.findIndex((v) => !v);
								firstEmpty = firstEmpty !== -1 ? firstEmpty : matchedSourceCols.length;
								matchedSourceCols[firstEmpty] = { ...col, score: 1 };
							}
						});
						matchedSourceCols = extendArray(
							Array.from(matchedSourceCols, (item) => item || { id: uuidv4(), name: '', score: 1 }),
							filterTableCols?.length ?? 0,
							{ id: uuidv4(), name: '', score: 1 }
						);

						isMatchingImportCols = {
							filename: file.name,
							rows: results.data as any[],
							cols: matchedSourceCols.map(({ id, name }) => ({ id, name }))
						};
					} else {
						uploadImportFile(file);
					}
				}
			});
		};
		fileInput.click();
	}

	async function uploadImportFile(file: File) {
		if (!tableData) return;

		const formData = new FormData();
		formData.append('file', file, file.name);
		formData.append('table_id', tableData.id);

		$showLoadingOverlay = true;

		try {
			const response = await axios.post(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/import_data`,
				formData,
				{
					headers: {
						'Content-Type': 'multipart/form-data',
						'x-project-id': page.params.project_id
					}
				}
			);
			if (response.status != 200) {
				logger.error(toUpper(`${tableType}TBL_TBL_IMPORT`), response.data);
				alert(
					'Failed to import data: ' +
						(response.data.message || JSON.stringify(response.data)) +
						`\nRequest ID: ${response.data.request_id}`
				);
			} else {
				await refetchTable();

				if (response.data.err_message) {
					alert(
						'Error while uploading file: ' + response.data.message ||
							JSON.stringify(response.data) + `\nRequest ID: ${response.data.request_id}`
					);
				}
			}
		} catch (err) {
			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error(toUpper(`${tableType}TBL_TBL_IMPORTUPLOAD`), err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}

		$showLoadingOverlay = false;
	}

	async function handleExportRows() {
		if (!tableData || $showLoadingOverlay) return;

		$showLoadingOverlay = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/export_data?${new URLSearchParams([
				['table_id', tableData.id]
			])}`,
			{
				headers: {
					'x-project-id': page.params.project_id ?? ''
				}
			}
		);

		if (response.ok) {
			const responseBody = await response.text();
			textToFileDownload(`${tableData.id}`, responseBody);
		} else {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_TBL_EXPORTROWS`), responseBody);
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
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="action"
				title="Table actions"
				class="aspect-square h-8 w-auto p-0 sm:h-9"
			>
				<FourCircles class="h-6 text-[#667085]" />
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>
	<DropdownMenu.Content
		data-testid="table-actions-dropdown"
		align="end"
		class="max-w-[20rem] p-2 text-[#344054]"
	>
		<DropdownMenu.Group class="flex flex-col gap-1 py-1 [&>*]:border [&>*]:border-[#E4E7EC]">
			<DropdownMenu.Item onclick={handleImportTable}>
				<ImportIcon class="mb-[2px] mr-2 h-4 w-4" />
				<span class="grow text-center"> Import rows </span>
			</DropdownMenu.Item>
			<DropdownMenu.Item onclick={handleExportRows}>
				<ExportIcon class="mb-[2px] mr-2 h-4 w-4" />
				<span class="grow text-center"> Export rows (.csv) </span>
			</DropdownMenu.Item>
			<ExportTableButton tableId={tableData?.id} {tableType}>
				{#snippet children({ handleExportTable })}
					<DropdownMenu.Item onclick={handleExportTable}>
						<ExportIcon class="mb-[2px] mr-2 h-4 w-4" />
						<span class="grow text-center"> Export table </span>
					</DropdownMenu.Item>
				{/snippet}
			</ExportTableButton>
		</DropdownMenu.Group>

		<DropdownMenu.Separator class="-mx-2 my-2" />

		<DropdownMenu.Group class="flex flex-col gap-1 py-1 [&>*]:border [&>*]:border-[#E4E7EC]">
			<DropdownMenu.Item
				onclick={() => (isDeletingTable = page.params.table_id ?? null)}
				class="text-[#D92D20] hover:!bg-[#FEF3F2] hover:!text-[#D92D20] data-[highlighted]:bg-[#FEF3F2] data-[highlighted]:text-[#D92D20]"
			>
				<Trash2 class="mb-[2px] mr-2 h-4 w-4" />
				<span class="grow text-center"> Delete table </span>
			</DropdownMenu.Item>
		</DropdownMenu.Group>
	</DropdownMenu.Content>
</DropdownMenu.Root>

<ColumnMatchDialog bind:isMatchingImportCols {tableData} {uploadImportFile} />
<DeleteTableDialog
	{tableType}
	bind:isDeletingTable
	deletedCb={(success) => {
		if (success) {
			goto(`/project/${page.params.project_id}/${tableType}-table`);
		}
	}}
/>
