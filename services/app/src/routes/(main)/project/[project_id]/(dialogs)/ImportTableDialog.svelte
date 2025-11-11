<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import axios, { CanceledError } from 'axios';
	import logger from '$lib/logger';

	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';

	interface Props {
		isImportingTable: File | null;
		tableType: 'action' | 'knowledge' | 'chat';
		refetchTables: () => Promise<void>;
	}

	let { isImportingTable = $bindable(), tableType, refetchTables }: Props = $props();

	let isLoading = $state(false);
	let uploadProgress: number | null = $state(null);

	async function handleImportTable(e: SubmitEvent & { currentTarget: HTMLFormElement }) {
		e.preventDefault();
		if (!isImportingTable) return;

		const tableId = new FormData(e.currentTarget).get('table_id') as string;

		if (!tableId.trim()) {
			toast.error('Table ID is required', {
				id: 'table-id-req'
			});
		}

		const formData = new FormData();
		formData.append('file', isImportingTable);
		formData.append('table_id_dst', tableId);

		isLoading = true;
		try {
			const uploadRes = await axios.post(
				`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/import`,
				formData,
				{
					headers: {
						'Content-Type': 'multipart/form-data'
					},
					onUploadProgress: (progressEvent) => {
						if (!progressEvent.total) return;
						const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
						uploadProgress = percentCompleted;
					}
				}
			);

			if (uploadRes.status != 200) {
				logger.error(toUpper(`${tableType}TBL_IMPORT_UPLOAD`), {
					file: isImportingTable.name,
					response: uploadRes.data
				});
				alert(
					'Failed to upload file: ' +
						(uploadRes.data.message || JSON.stringify(uploadRes.data)) +
						`\nRequest ID: ${uploadRes.data.request_id}`
				);
			} else {
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
				logger.error(toUpper(`${tableType}TBL_IMPORT_UPLOAD`), err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}

		await refetchTables();
		isLoading = false;
		isImportingTable = null;
		uploadProgress = null;
	}
</script>

<Dialog.Root bind:open={() => !!isImportingTable, () => (isImportingTable = null)}>
	<Dialog.Content
		data-testid="import-table-dialog"
		interactOutsideBehavior={isLoading ? 'ignore' : 'close'}
		escapeKeydownBehavior={isLoading ? 'ignore' : 'close'}
		class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
	>
		<Dialog.Header>Import table</Dialog.Header>

		<form
			id="importTableForm"
			onsubmit={handleImportTable}
			class="flex w-full grow flex-col gap-3 overflow-auto py-3"
		>
			<div class="flex w-full flex-col gap-2 px-4 text-center sm:px-6">
				<Label required for="table_id" class="text-xs sm:text-sm">Table ID</Label>

				<InputText
					autofocus
					disabled={isLoading}
					id="table_id"
					name="table_id"
					placeholder="Required"
					value={isImportingTable?.name
						?.split('.')
						?.slice(0, -1)
						?.join('.')
						?.replace(/^[._-]+|[._-]+$/g, '')
						?.replaceAll(' ', '_')}
				/>
			</div>

			{#if isImportingTable}
				<div class="flex w-full items-center px-4 text-sm sm:px-6">
					<div
						class="flex min-h-8 grow items-center gap-2 rounded-md bg-[#F2F4F7] px-4 py-3 data-dark:bg-[#42464e]"
					>
						<DocumentFilledIcon class="h-6" />

						<p title={isImportingTable.name} class="line-clamp-3 break-all text-start">
							{isImportingTable.name}
						</p>

						<!-- <div
											class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
										>
											<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
										</div> -->

						{#if uploadProgress}
							<div
								class="radial-progress my-2 ml-auto flex-[0_0_auto] text-secondary [transform:_scale(-1,_1)]"
								style="--value:{Math.floor(uploadProgress)}; --size:20px; --thickness: 5px;"
							></div>
						{:else}
							<Button
								onclick={() => {
									//@ts-ignore
									document.querySelector('input#action-tbl-import')?.click();
								}}
								type="button"
								class="ml-auto h-9 px-3.5"
							>
								Change
							</Button>
						{/if}
					</div>
				</div>
			{/if}
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="importTableForm"
					loading={isLoading}
					disabled={isLoading}
					class="relative grow px-6"
				>
					Import
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
