<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import debounce from 'lodash/debounce';
	import axios, { CanceledError } from 'axios';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { modelsAvailable } from '$globalStore';
	import { jamaiApiVersion, knowledgeTableFiletypes, tableIDPattern } from '$lib/constants';
	import logger from '$lib/logger';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import CheckIcon from '$lib/icons/CheckIcon.svelte';

	export let uploadFile = false;
	export let isAddingTable: boolean;
	export let refetchTables: (() => Promise<void>) | undefined = undefined;

	let container: HTMLDivElement;
	let tableId = '';
	let selectedModel = '';

	let filesDragover = false;
	let selectedFiles: File[] = [];
	let activeFile: { index: number; progress: number } | null = null;

	let isLoading = false;

	$: if (!isAddingTable) {
		tableId = '';
	}

	async function handleAddTable() {
		if (!tableId) return toast.error('Table ID is required', { id: 'table-id-req' });
		if (!selectedModel) return toast.error('Model not selected', { id: 'model-not-selected' });

		if (!tableIDPattern.test(tableId))
			return toast.error(
				'Table ID must contain only alphanumeric characters and underscores/hyphens/periods, and start and end with alphanumeric characters, between 1 and 100 characters.',
				{ id: 'table-id-invalid' }
			);

		if (uploadFile && selectedFiles.length === 0)
			return toast.error('No files selected to upload', { id: 'files-req' });

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				id: tableId,
				version: jamaiApiVersion,
				cols: [],
				embedding_model: selectedModel
			})
		});

		const responseBody = await response.json();
		if (!response.ok) {
			logger.error('KNOWTBL_TBL_ADD', responseBody);
			toast.error('Failed to add table', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			isLoading = false;
			return;
		}

		if (uploadFile) {
			for (const selectedFile of selectedFiles) {
				activeFile = { index: (activeFile?.index ?? -1) + 1, progress: 0 };

				const formData = new FormData();
				formData.append('file', selectedFile, selectedFile.name);
				formData.append('table_id', tableId);

				try {
					const uploadRes = await axios.post(
						`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/embed_file`,
						formData,
						{
							headers: {
								'Content-Type': 'multipart/form-data',
								'x-project-id': $page.params.project_id
							},
							onUploadProgress: (progressEvent) => {
								if (!progressEvent.total) return;
								const percentCompleted = Math.round(
									(progressEvent.loaded * 100) / progressEvent.total
								);
								activeFile = { index: activeFile?.index ?? -1, progress: percentCompleted };
							}
						}
					);

					if (uploadRes.status != 200) {
						logger.error('SELECTKT_UPLOAD_FAILED', {
							file: selectedFile.name,
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
						logger.error('SELECTKT_UPLOAD_FAILED', err?.response?.data);
						alert(
							'Failed to upload file: ' +
								//@ts-expect-error AxiosError
								(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
								//@ts-expect-error AxiosError
								`\nRequest ID: ${err?.response?.data?.request_id}`
						);
					}
				}
			}

			activeFile = null;
		}

		if (refetchTables) {
			await refetchTables();
			isAddingTable = false;
			tableId = '';
			selectedFiles = [];
			isLoading = false;
		} else {
			goto(`/project/${$page.params.project_id}/knowledge-table/${responseBody.id}`);
		}
	}

	async function handleFilesUpload(files: File[]) {
		container
			.querySelectorAll('input[type="file"]')
			.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (
			files.some(
				(file) => !knowledgeTableFiletypes.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(`Files must be of type: ${knowledgeTableFiletypes.join(', ').replaceAll('.', '')}`);
			return;
		}

		selectedFiles = [...selectedFiles, ...files];
	}

	const handleUploadClick = () =>
		(document.querySelector('input[type="file"]') as HTMLElement).click();
	const handleDragLeave = () => (filesDragover = false);
</script>

<Dialog.Root closeOnEscape={!isLoading} closeOnOutsideClick={!isLoading} bind:open={isAddingTable}>
	<Dialog.Content data-testid="new-table-dialog" class="max-h-[90vh] w-[clamp(0px,30rem,100%)]">
		<Dialog.Header disabledClose={isLoading}>New knowledge table</Dialog.Header>

		<div bind:this={container} class="grow flex flex-col gap-3 py-3 w-full overflow-auto">
			<div class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center">
				<span class="font-medium text-left text-xs sm:text-sm text-black"> Table ID* </span>

				<InputText
					disabled={isLoading}
					bind:value={tableId}
					name="table_id"
					placeholder="Required"
				/>
			</div>

			<div data-testid="model-select-btn" class="flex flex-col gap-1 px-4 sm:px-6">
				<span class="font-medium text-left text-xs sm:text-sm text-black"> Embedding Model* </span>

				<ModelSelect
					disabled={isLoading}
					capabilityFilter="embed"
					sameWidth={true}
					bind:selectedModel
					buttonText={($modelsAvailable.find((model) => model.id == selectedModel)?.name ??
						selectedModel) ||
						'Select model'}
					class="{!selectedModel
						? 'italic text-muted-foreground'
						: ''} bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent"
				/>
			</div>

			{#if uploadFile}
				<div class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center">
					<span class="font-medium text-left text-xs sm:text-sm text-black">
						Upload document*
					</span>

					{#if selectedFiles.length === 0}
						<button
							on:click={handleUploadClick}
							on:dragover|preventDefault={(e) => {
								if (e.dataTransfer?.items) {
									if ([...e.dataTransfer.items].some((item) => item.kind === 'file')) {
										filesDragover = true;
									}
								}
							}}
							on:dragleave={debounce(handleDragLeave, 50)}
							on:drop|preventDefault={(e) => {
								filesDragover = false;
								if (e.dataTransfer?.items) {
									handleFilesUpload(
										[...e.dataTransfer.items]
											.map((item) => {
												if (item.kind === 'file') {
													const itemFile = item.getAsFile();
													if (itemFile) {
														return itemFile;
													} else {
														return [];
													}
												} else {
													return [];
												}
											})
											.flat()
									);
								} else {
									handleFilesUpload([...(e.dataTransfer?.files ?? [])]);
								}
							}}
							class="flex flex-col items-center justify-center px-3 sm:px-16 h-96 border-2 {filesDragover
								? 'border-[#BF416E]'
								: 'border-[#D0D5DD]'} border-dashed rounded transition-colors"
						>
							<svg
								width="41"
								height="43"
								viewBox="0 0 41 43"
								fill="none"
								xmlns="http://www.w3.org/2000/svg"
							>
								<path
									fill-rule="evenodd"
									clip-rule="evenodd"
									d="M1.96447 1.81802C2.90213 0.974105 4.17393 0.5 5.5 0.5H25.5C25.942 0.5 26.366 0.658035 26.6785 0.939341L40.012 12.9394C40.3243 13.2206 40.5 13.6022 40.5 14V38C40.5 39.1934 39.9733 40.3382 39.0357 41.1821C38.098 42.026 36.826 42.5 35.5 42.5H5.5C4.1739 42.5 2.90213 42.026 1.96447 41.1821C1.0268 40.3382 0.5 39.1934 0.5 38V5C0.5 3.80654 1.0268 2.66193 1.96447 1.81802ZM21.1232 10.7992L21.4696 11.111C21.8579 11.339 22.19 11.638 22.4434 11.9874L28.6232 17.5492C29.219 18.0854 29.3972 18.8919 29.0748 19.5925C28.7523 20.2932 27.9927 20.75 27.15 20.75H22.9834V31.625C22.9834 33.2819 21.491 34.625 19.6501 34.625C17.8091 34.625 16.3167 33.2819 16.3167 31.625V20.75H12.15C11.3074 20.75 10.5477 20.2932 10.2253 19.5925C9.90283 18.8919 10.0811 18.0854 10.6769 17.5492L16.8568 11.9873C17.1101 11.6379 17.4422 11.3391 17.8304 11.111L18.1769 10.7992C18.5676 10.4475 19.0975 10.25 19.65 10.25C20.2026 10.25 20.7325 10.4475 21.1232 10.7992Z"
									fill="#BF416E"
								/>
							</svg>

							<p class="mt-3 text-[#344054] font-medium">
								Drag & Drop
								<br /> or
								<span class="text-[#BF416E]">browse</span>
							</p>

							<p class="text-[#98A2B3] text-xs">Supports: {knowledgeTableFiletypes.join(', ')}</p>
						</button>
					{:else}
						<ul
							class="flex flex-col items-start pl-8 pr-3 py-2 mb-1 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md list-disc"
						>
							{#each selectedFiles as selectedFile, index}
								<li class="mb-0.5 last:mb-0 w-full">
									<div
										class="grid grid-cols-[minmax(0,auto)_min-content] items-center gap-2 min-h-8"
									>
										<p title={selectedFile.name} class="text-start line-clamp-3 break-all">
											{selectedFile.name}
										</p>

										<!-- <div
											class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
										>
											<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
										</div> -->

										{#if !isLoading}
											<Button
												variant="ghost"
												title="Remove file"
												on:click={() =>
													(selectedFiles = selectedFiles.filter((_, idx) => index !== idx))}
												class=" p-0 h-8 w-8 aspect-square rounded-full"
											>
												<CloseIcon class="h-5" />
											</Button>
										{:else if index < (activeFile?.index ?? -1)}
											<div
												class="flex-[0_0_auto] flex items-center justify-center p-1 bg-[#2ECC40] data-dark:bg-[#54D362] rounded-full"
											>
												<CheckIcon class="w-3 stroke-white data-dark:stroke-black stroke-[3]" />
											</div>
										{:else if index >= (activeFile?.index ?? -1)}
											<div
												class="flex-[0_0_auto] radial-progress text-secondary [transform:_scale(-1,_1)]"
												style="--value:{Math.floor(
													activeFile?.index === index ? activeFile?.progress : 0
												)}; --size:20px; --thickness: 5px;"
											/>
										{/if}
									</div>
								</li>
							{/each}
						</ul>

						{#if !isLoading}
							<Button
								on:click={handleUploadClick}
								type="button"
								disabled={isLoading}
								class="relative px-6 w-min rounded-full"
							>
								Upload more
							</Button>
						{/if}
					{/if}

					<input
						type="file"
						disabled={isLoading}
						accept={knowledgeTableFiletypes.join(',')}
						on:change|preventDefault={(e) => handleFilesUpload([...(e.currentTarget.files ?? [])])}
						multiple
						class="max-h-[0] !p-0 !border-none overflow-hidden"
					/>
				</div>
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button
						builders={[builder]}
						disabled={isLoading}
						variant="link"
						type="button"
						class="grow px-6"
					>
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleAddTable}
					type="button"
					disabled={isLoading}
					loading={isLoading}
					class="relative grow px-6 rounded-full"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
