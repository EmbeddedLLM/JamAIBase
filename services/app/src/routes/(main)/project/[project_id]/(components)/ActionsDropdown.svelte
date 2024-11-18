<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import xorWith from 'lodash/xorWith';
	import { v4 as uuidv4 } from 'uuid';
	import axios from 'axios';
	import Papa from 'papaparse';
	import Fuse from 'fuse.js';
	import { DropdownMenu as DropdownMenuPrimitive } from 'bits-ui';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { showLoadingOverlay } from '$globalStore';
	import { extendArray, textToFileDownload } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable } from '$lib/types';

	import { ColumnMatchDialog, DeleteTableDialog } from '../(dialogs)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ImportIcon from '$lib/icons/ImportIcon.svelte';
	import ExportIcon from '$lib/icons/ExportIcon.svelte';
	import HamburgerIcon from '$lib/icons/HamburgerIcon.svelte';
	import AddColumnIcon from '$lib/icons/AddColumnIcon.svelte';
	import Trash_2 from 'lucide-svelte/icons/trash-2';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable | undefined;
	export let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean };
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;

	let isMatchingImportCols: {
		filename: string;
		rows: Record<string, string>[];
		cols: { id: string; name: string }[];
	} | null = null;
	let isDeletingTable: string | null = null;

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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/import_data`,
				formData,
				{
					headers: {
						'Content-Type': 'multipart/form-data',
						'x-project-id': $page.params.project_id
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
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableData.id}/export_data`,
			{
				headers: {
					'x-project-id': $page.params.project_id
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
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		$showLoadingOverlay = false;
	}

	async function handleExportTable() {
		if (!tableData || $showLoadingOverlay) return;

		if (PUBLIC_IS_LOCAL === 'false') {
			window
				.open(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableData.id}/export`, '_blank')
				?.focus();
		} else {
			$showLoadingOverlay = true;

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableData.id}/export`,
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
						`${tableData.id}.parquet`,
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

<DropdownMenu.Root>
	<DropdownMenu.Trigger asChild let:builder>
		<Button
			builders={[builder]}
			variant="ghost"
			title="Table actions"
			class="p-0 h-8 sm:h-9 w-auto aspect-square"
		>
			<HamburgerIcon class="h-6 text-[#667085]" />
		</Button>
	</DropdownMenu.Trigger>
	<DropdownMenu.Content
		data-testid="table-actions-dropdown"
		alignOffset={-40}
		transitionConfig={{ x: 5, y: -10 }}
		class="p-2 text-[#344054]"
	>
		<DropdownMenu.Group class="flex flex-col gap-2 py-1 text-sm">
			<span class="ml-1 text-[#98A2B3]">
				Order by
				<span class="font-medium text-[#667085]">Last modified</span>
			</span>

			<div
				style="grid-template-columns: repeat(2, minmax(5rem, 1fr));"
				class="relative grid place-items-center w-full bg-[#E4E7EC] data-dark:bg-gray-700 rounded-[3px] p-0.5 after:content-[''] after:absolute after:left-0.5 after:top-1/2 after:-translate-y-1/2 after:z-0 after:h-[calc(100%_-_4px)] after:w-1/2 after:pointer-events-none after:bg-white after:rounded-[3px] after:transition-transform after:duration-200 {$page.url.searchParams.get(
					'asc'
				) === '1'
					? 'after:translate-x-0'
					: 'after:translate-x-[calc(100%_-_4px)]'}"
			>
				<DropdownMenuPrimitive.Item
					on:click={() => {
						const query = new URLSearchParams($page.url.searchParams.toString());
						query.set('asc', '1');
						goto(`?${query.toString()}`, { replaceState: true });
					}}
					class="z-10 transition-colors ease-in-out rounded-[3px] px-4 py-1 w-full text-center {$page.url.searchParams.get(
						'asc'
					) === '1'
						? 'text-[#667085]'
						: 'text-[#98A2B3]'} cursor-pointer"
				>
					Ascending
				</DropdownMenuPrimitive.Item>

				<DropdownMenuPrimitive.Item
					on:click={() => {
						const query = new URLSearchParams($page.url.searchParams.toString());
						query.delete('asc');
						goto(`?${query.toString()}`, { replaceState: true });
					}}
					class="z-10 transition-colors ease-in-out rounded-[3px] px-4 py-1 w-full text-center {$page.url.searchParams.get(
						'asc'
					) !== '1'
						? 'text-[#667085]'
						: 'text-[#98A2B3]'} cursor-pointer"
				>
					Descending
				</DropdownMenuPrimitive.Item>
			</div>
		</DropdownMenu.Group>

		<DropdownMenu.Separator class="-mx-2 my-2" />

		{#if tableType !== 'chat' || !tableData?.parent_id}
			<DropdownMenu.Group
				class="grid grid-cols-2 gap-2 py-1 [&>*]:border [&>*]:border-[#E4E7EC] [&>*]:flex-col [&>*]:px-5 [&>*]:py-3"
			>
				<DropdownMenu.Item on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}>
					<AddColumnIcon class="mb-1" />
					<span class="text-center">
						Add
						<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
						<br />
						column
					</span>
				</DropdownMenu.Item>
				<DropdownMenu.Item on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}>
					<AddColumnIcon class="mb-1" />
					<span class="text-center">
						Add
						<span class="text-[#950048] data-dark:text-[#950048]">output</span>
						<br />
						column
					</span>
				</DropdownMenu.Item>
			</DropdownMenu.Group>

			<DropdownMenu.Separator class="-mx-2 my-2" />
		{/if}

		<DropdownMenu.Group class="flex flex-col gap-1 py-1 [&>*]:border [&>*]:border-[#E4E7EC]">
			<DropdownMenu.Item on:click={handleImportTable}>
				<ImportIcon class="h-4 w-4 mr-2 mb-[2px]" />
				<span class="grow text-center"> Import rows </span>
			</DropdownMenu.Item>
			<DropdownMenu.Item on:click={handleExportRows}>
				<ExportIcon class="h-4 w-4 mr-2 mb-[2px]" />
				<span class="grow text-center"> Export rows (.csv) </span>
			</DropdownMenu.Item>
			<DropdownMenu.Item on:click={handleExportTable}>
				<ExportIcon class="h-4 w-4 mr-2 mb-[2px]" />
				<span class="grow text-center"> Export table </span>
			</DropdownMenu.Item>
		</DropdownMenu.Group>

		<DropdownMenu.Separator class="-mx-2 my-2" />

		<DropdownMenu.Group class="flex flex-col gap-1 py-1 [&>*]:border [&>*]:border-[#E4E7EC]">
			<DropdownMenu.Item
				on:click={() => (isDeletingTable = $page.params.table_id)}
				class="text-[#D92D20] hover:!text-[#D92D20] hover:!bg-[#FEF3F2]"
			>
				<Trash_2 class="h-4 w-4 mr-2 mb-[2px]" />
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
			goto(`/project/${$page.params.project_id}/${tableType}-table`);
		}
	}}
/>
