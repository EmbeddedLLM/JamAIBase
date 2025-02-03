<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/stores';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { modelsAvailable } from '$globalStore';
	import { insertAtCursor } from '$lib/utils';
	import { columnIDPattern, genTableDTypes, jamaiApiVersion } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import Range from '$lib/components/Range.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	export let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean };
	export let tableType: 'action' | 'knowledge' | 'chat';
	export let tableData: GenTable | undefined;
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;

	let usableColumns: GenTableCol[] = [];
	$: isAddingColumn, resetValues();
	const resetValues = () => {
		if (isAddingColumn.showDialog) {
			if (isAddingColumn.type === 'output') {
				usableColumns =
					tableData?.cols?.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? [];
			}

			selectedDatatype = 'str';
		}
	};

	let form: HTMLFormElement;
	let isLoading = false;
	let columnName = '';
	let selectedDatatype: (typeof genTableDTypes)[string] | '' = '';
	let selectedModel = '';
	let temperature = '1';
	let maxTokens = '1000';
	let topP = '0.1';
	let prompt = '';
	let systemPrompt = '';
	let isMultiturn = false;
	let selectedSourceColumn = '';

	async function handleAddColumn() {
		if (!columnName || !selectedDatatype) {
			return toast.error('Please fill in all fields', { id: 'all-fields-req' });
		}

		if (!columnIDPattern.test(columnName))
			return toast.error(
				'Column name must contain only alphanumeric characters and underscores/hyphens/spaces, and start and end with alphanumeric characters between 1 and 100 characters long.',
				{ id: 'column-name-invalid' }
			);

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/columns/add`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				id: $page.params.table_id,
				version: jamaiApiVersion,
				cols: [
					{
						id: columnName,
						dtype: selectedDatatype.replace('_code', ''),
						vlen: 0,
						gen_config: (isAddingColumn.type == 'output'
							? selectedDatatype.endsWith('_code')
								? {
										object: 'gen_config.code',
										source_column: selectedSourceColumn
									}
								: {
										object: 'gen_config.llm',
										model: selectedModel,
										system_prompt: systemPrompt,
										prompt,
										temperature: parseFloat(temperature),
										max_tokens: parseInt(maxTokens),
										top_p: parseFloat(topP),
										multi_turn: isMultiturn
									}
							: null) satisfies GenTableCol['gen_config']
					}
				]
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_ADD`), responseBody);
			toast.error('Failed to add column', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		} else {
			refetchTable();
			isAddingColumn = { ...isAddingColumn, showDialog: false };
			columnName = '';
			selectedDatatype = '';
		}

		isLoading = false;
	}
</script>

<Dialog.Root
	open={isAddingColumn.showDialog}
	onOpenChange={(e) => {
		if (!e) {
			isAddingColumn = { ...isAddingColumn, showDialog: false };
		}
	}}
>
	<Dialog.Content
		data-testid="new-column-dialog"
		class="max-h-[80vh] sm:max-h-[90vh] {isAddingColumn.type === 'input' ||
		selectedDatatype.endsWith('_code')
			? 'w-[clamp(0px,35rem,100%)]'
			: 'w-[clamp(0px,65rem,100%)]'}"
	>
		<Dialog.Header>New {isAddingColumn.type} column</Dialog.Header>

		<form
			bind:this={form}
			on:submit|preventDefault={handleAddColumn}
			class="grow flex flex-col gap-3 py-3 w-full overflow-auto"
		>
			<div class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center">
				<label for="column_id" class="font-medium text-left text-xs sm:text-sm text-black">
					Column ID*
				</label>

				<InputText bind:value={columnName} id="column_id" placeholder="Required" />
			</div>

			<div
				data-testid="datatype-select-btn"
				class="flex flex-col gap-1 px-4 sm:px-6 w-full text-center"
			>
				<span class="font-medium text-left text-xs sm:text-sm text-black">Data type*</span>

				<Select.Root
					selected={{ value: selectedDatatype }}
					onSelectedChange={(v) => {
						if (v) {
							selectedDatatype = v.value;
						}
					}}
				>
					<Select.Trigger asChild let:builder>
						<Button
							builders={[builder]}
							variant="outline-neutral"
							title="Select data type"
							class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full {!selectedDatatype
								? 'italic text-muted-foreground'
								: ''} bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent rounded-md"
						>
							<span class="w-full whitespace-nowrap line-clamp-1 font-normal text-left">
								{genTableDTypes[selectedDatatype]
									? genTableDTypes[selectedDatatype]
									: 'Select data type'}
							</span>

							<ChevronDown class="h-4 w-4" />
						</Button>
					</Select.Trigger>
					<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
						{#each Object.keys(genTableDTypes).filter((dtype) => (isAddingColumn.type === 'output' || !dtype.endsWith('_code')) && (isAddingColumn.type === 'input' || dtype.startsWith('str') || dtype === 'file_code')) as dType}
							<Select.Item
								value={dType}
								label={genTableDTypes[dType]}
								class="flex justify-between gap-10 cursor-pointer"
							>
								{genTableDTypes[dType]}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			{#if isAddingColumn.type == 'output'}
				{#if !selectedDatatype.endsWith('_code')}
					<div class="flex flex-col gap-1 px-4 sm:px-6">
						<span class="font-medium text-left text-xs sm:text-sm text-black">Models</span>

						<ModelSelect
							capabilityFilter="chat"
							sameWidth={true}
							{selectedModel}
							selectCb={(model) => {
								selectedModel = model;

								const modelDetails = $modelsAvailable.find((val) => val.id == model);
								if (modelDetails && parseInt(maxTokens) > modelDetails.context_length) {
									maxTokens = modelDetails.context_length.toString();
								}
							}}
							buttonText={($modelsAvailable.find((model) => model.id == selectedModel)?.name ??
								selectedModel) ||
								'Select model'}
							class="bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent"
						/>
					</div>

					<div class="grid grid-cols-1 xs:grid-cols-3 gap-3 px-4 sm:px-6 w-full text-center">
						<div class="flex flex-col gap-1">
							<label for="temperature" class="font-medium text-left text-xs sm:text-sm text-black">
								Temperature
							</label>

							<input
								id="temperature"
								type="number"
								step=".01"
								bind:value={temperature}
								on:change={(e) => {
									const value = parseFloat(e.currentTarget.value);

									if (isNaN(value)) {
										temperature = '1';
									} else if (value < 0.01) {
										temperature = '0.01';
									} else if (value > 1) {
										temperature = '1';
									} else {
										temperature = value.toFixed(2);
									}
								}}
								class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
							/>

							<Range bind:value={temperature} min=".01" max="1" step=".01" />
						</div>

						<div class="flex flex-col gap-1">
							<label for="max_tokens" class="font-medium text-left text-xs sm:text-sm text-black">
								Max tokens
							</label>

							<input
								id="max_tokens"
								type="number"
								bind:value={maxTokens}
								on:change={(e) => {
									const value = parseInt(e.currentTarget.value);
									const model = $modelsAvailable.find((model) => model.id == selectedModel);

									if (isNaN(value)) {
										maxTokens = '1';
									} else if (value < 1 || value > 1e20) {
										maxTokens = '1';
									} else if (model && value > model.context_length) {
										maxTokens = model.context_length.toString();
									} else {
										maxTokens = value.toString();
									}
								}}
								class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
							/>

							<Range
								bind:value={maxTokens}
								min="1"
								max={$modelsAvailable.find((model) => model.id == selectedModel)?.context_length}
								step="1"
							/>
						</div>

						<div class="flex flex-col gap-1">
							<label for="top_p" class="font-medium text-left text-xs sm:text-sm text-black">
								Top-p
							</label>

							<input
								id="top_p"
								type="number"
								step=".001"
								bind:value={topP}
								on:change={(e) => {
									const value = parseFloat(e.currentTarget.value);

									if (isNaN(value)) {
										topP = '1';
									} else if (value < 0.01) {
										topP = '0.001';
									} else if (value > 1) {
										topP = '1';
									} else {
										topP = value.toFixed(3);
									}
								}}
								class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
							/>

							<Range bind:value={topP} min=".001" max="1" step=".001" />
						</div>

						<div class="flex flex-col gap-1">
							<label
								for="multiturn-enabled"
								class="font-medium text-left text-xs sm:text-sm text-black"
							>
								Multi-turn chat
							</label>

							<div
								class="flex items-center gap-2 px-3 py-2 bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md"
							>
								<Switch
									id="multiturn-enabled"
									name="multiturn-enabled"
									class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
									bind:checked={isMultiturn}
								/>
							</div>
						</div>
					</div>

					<div class="grid grid-rows-[min-content_1fr] gap-1 px-4 sm:px-6">
						<label for="add_prompt" class="font-medium text-xs sm:text-sm text-black">
							Customize prompt
						</label>

						<div class="flex items-center gap-1 flex-wrap">
							<span class="text-xxs sm:text-xs text-[#999]">Columns:</span>
							{#each usableColumns as column}
								<Button
									variant="ghost"
									class="px-1.5 py-0.5 sm:py-1 h-[unset] !text-xxs sm:!text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]"
									on:click={() => {
										insertAtCursor(
											// @ts-ignore
											document.getElementById('add_prompt'),
											`\${${column.id}}`
										);
										// @ts-ignore
										prompt = document.getElementById('add_prompt')?.value ?? prompt;
										document.getElementById('add_prompt')?.focus();
									}}
								>
									{column.id}
								</Button>
							{/each}
						</div>

						<textarea
							bind:value={prompt}
							id="add_prompt"
							placeholder="Enter prompt"
							class="p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-transparent outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						></textarea>
					</div>

					<div class="grid grid-rows-[min-content_1fr] gap-1 px-4 sm:px-6">
						<label for="system_prompt" class="font-medium text-xs sm:text-sm text-black">
							Customize system prompt
						</label>

						<textarea
							bind:value={systemPrompt}
							id="system_prompt"
							placeholder="Enter system prompt"
							class="p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-transparent outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						></textarea>
					</div>
				{:else}
					<div class="flex flex-col gap-1 px-4 sm:px-6">
						<span class="font-medium text-left text-xs sm:text-sm text-black">Source column</span>

						<Select.Root
							selected={{ value: selectedSourceColumn }}
							onSelectedChange={(v) => {
								if (v) {
									selectedSourceColumn = v.value;
								}
							}}
						>
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<Select.Trigger asChild let:builder>
								<Button
									builders={[builder]}
									variant="outline-neutral"
									class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent disabled:opacity-100 rounded-md {selectedSourceColumn
										? ''
										: 'italic text-muted-foreground hover:text-muted-foreground'}"
								>
									<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
										{selectedSourceColumn || 'Select source column'}
									</span>

									<ChevronDown class="h-4 w-4" />
								</Button>
							</Select.Trigger>
							<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
								{#each usableColumns ?? [] as column}
									<Select.Item
										value={column.id}
										label={column.id}
										class="flex justify-between gap-10 cursor-pointer"
									>
										{column.id}
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
				{/if}
			{/if}

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoading}
				disabled={isLoading}
				class="hidden relative grow px-6 rounded-full"
			>
				Add
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
					type="button"
					loading={isLoading}
					disabled={isLoading}
					on:click={() => form.requestSubmit()}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
