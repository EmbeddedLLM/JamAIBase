<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import axios, { CanceledError } from 'axios';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { page } from '$app/stores';
	import logger from '$lib/logger';

	import { toast } from 'svelte-sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DocumentFilledIcon from '$lib/icons/DocumentFilledIcon.svelte';
	import { tick } from 'svelte';

	export let isImportingTable: File | null;
	export let tableType: 'action' | 'knowledge' | 'chat';
	export let refetchTables: () => Promise<void>;

	let form: HTMLFormElement;
	let isLoading = false;
	let uploadProgress: number | null = null;

	async function handleImportTable(e: SubmitEvent & { currentTarget: HTMLFormElement }) {
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
				`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/import`,
				formData,
				{
					headers: {
						'Content-Type': 'multipart/form-data',
						'x-project-id': $page.params.project_id
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

<Dialog.Root
	closeOnEscape={!isLoading}
	closeOnOutsideClick={!isLoading}
	open={!!isImportingTable}
	onOpenChange={(e) => {
		if (!e) {
			isImportingTable = null;
		}
	}}
>
	<Dialog.Content data-testid="import-table-dialog" class="max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>Import table</Dialog.Header>

		<form
			bind:this={form}
			on:submit|preventDefault={handleImportTable}
			class="grow flex flex-col gap-3 py-3 w-full overflow-auto"
		>
			<div class="flex flex-col gap-2 px-4 sm:px-6 w-full text-center">
				<span class="font-medium text-left text-xs sm:text-sm text-black">Table ID*</span>

				<InputText
					autofocus
					disabled={isLoading}
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
				<div class="flex items-center px-4 sm:px-6 w-full text-sm">
					<div
						class="grow flex items-center gap-2 px-4 py-3 min-h-8 bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md"
					>
						<DocumentFilledIcon class="h-6" />

						<p title={isImportingTable.name} class="text-start line-clamp-3 break-all">
							{isImportingTable.name}
						</p>

						<!-- <div
											class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
										>
											<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
										</div> -->

						{#if uploadProgress}
							<div
								class="flex-[0_0_auto] ml-auto my-2 radial-progress text-secondary [transform:_scale(-1,_1)]"
								style="--value:{Math.floor(uploadProgress)}; --size:20px; --thickness: 5px;"
							></div>
						{:else}
							<Button
								on:click={() => {
									//@ts-ignore
									document.querySelector('input#action-tbl-import')?.click();
								}}
								type="button"
								class="ml-auto px-3.5 h-9 rounded-full"
							>
								Change
							</Button>
						{/if}
					</div>
				</div>
			{/if}

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoading}
				disabled={isLoading}
				class="hidden relative grow px-6 rounded-full"
			>
				Import
			</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={() => form.requestSubmit()}
					type="button"
					loading={isLoading}
					disabled={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Import
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
