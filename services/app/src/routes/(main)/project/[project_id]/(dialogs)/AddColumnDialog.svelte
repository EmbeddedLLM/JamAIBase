<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/state';
	import { modelsAvailable } from '$globalStore';
	import { insertAtCursor } from '$lib/utils';
	import { columnIDPattern, genTableDTypes, jamaiApiVersion } from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import Range from '$lib/components/Range.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	interface Props {
		isAddingColumn: { type: 'input' | 'output'; showDialog: boolean };
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	}

	let { isAddingColumn = $bindable(), tableType, tableData, refetchTable }: Props = $props();

	let usableColumns: GenTableCol[] = $state([]);
	const resetValues = () => {
		if (isAddingColumn.showDialog) {
			if (isAddingColumn.type === 'output') {
				usableColumns =
					tableData?.cols?.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? [];
			}

			selectedDatatype = 'str';
		}
	};
	$effect(() => {
		isAddingColumn;
		resetValues();
	});

	let isLoading = $state(false);
	let columnName = $state('');
	let selectedDatatype: (typeof genTableDTypes)[string] | '' = $state('');
	let selectedModel = $state('');
	let temperature = $state('1');
	let maxTokens = $state('1000');
	let topP = $state('0.1');
	let prompt = $state('');
	let systemPrompt = $state('');
	let isMultiturn = $state(false);
	let selectedSourceColumn = $state('');

	async function handleAddColumn(e: Event) {
		e.preventDefault();
		if (!columnName || !selectedDatatype) {
			return toast.error('Please fill in all fields', { id: 'all-fields-req' });
		}

		if (!columnIDPattern.test(columnName))
			return toast.error(
				'Column name must have at least 1 character and up to 46 characters, start with an alphabet or number, and end with an alphabet or number or these symbols: .?!()-. Characters in the middle can include space and these symbols: .?!@#$%^&*_()-.',
				{ id: 'column-name-invalid' }
			);

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/columns/add`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
				},
				body: JSON.stringify({
					id: page.params.table_id,
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
			}
		);

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_ADD`), responseBody);
			toast.error('Failed to add column', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
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
	bind:open={() => isAddingColumn.showDialog,
	(v) => (isAddingColumn = { ...isAddingColumn, showDialog: v })}
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
			id="addColumnForm"
			onsubmit={handleAddColumn}
			class="flex w-full grow flex-col gap-3 overflow-auto py-3"
		>
			<div class="w-full space-y-1 px-4 sm:px-6">
				<Label required for="column_id" class="text-xs sm:text-sm">Column ID</Label>

				<InputText bind:value={columnName} id="column_id" placeholder="Required" />
			</div>

			<div data-testid="datatype-select-btn" class="w-full space-y-1 px-4 sm:px-6">
				<Label required for="column_datatype" class="text-xs sm:text-sm">Data type</Label>

				<Select.Root type="single" bind:value={selectedDatatype}>
					<Select.Trigger
						id="column_datatype"
						title="Select data type"
						class="flex h-10 min-w-full items-center justify-between gap-8 pl-3 pr-2 {!selectedDatatype
							? 'italic text-muted-foreground'
							: ''} border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
					>
						{#snippet children()}
							<span class="line-clamp-1 w-full whitespace-nowrap text-left font-normal">
								{genTableDTypes[selectedDatatype]
									? genTableDTypes[selectedDatatype]
									: 'Select data type'}
							</span>
						{/snippet}
					</Select.Trigger>
					<Select.Content
						data-testid="datatype-select-list"
						side="bottom"
						class="max-h-64 overflow-y-auto"
					>
						{#each Object.keys(genTableDTypes).filter((dtype) => (isAddingColumn.type === 'output' || !dtype.endsWith('_code')) && (isAddingColumn.type === 'input' || dtype.startsWith('str') || dtype === 'file_code')) as dType}
							<Select.Item
								value={dType}
								label={genTableDTypes[dType]}
								class="flex cursor-pointer justify-between gap-10"
							>
								{genTableDTypes[dType]}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			{#if isAddingColumn.type == 'output'}
				{#if !selectedDatatype.endsWith('_code')}
					<div class="space-y-1 px-4 sm:px-6">
						<Label class="text-xs sm:text-sm">Models</Label>

						<ModelSelect
							capabilityFilter="chat"
							bind:selectedModel
							selectCb={(model) => {
								const modelDetails = $modelsAvailable.find((val) => val.id == model);
								if (modelDetails && parseInt(maxTokens) > modelDetails.context_length) {
									maxTokens = modelDetails.context_length.toString();
								}
							}}
							class="border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
						/>
					</div>

					<div class="grid w-full grid-cols-1 gap-3 px-4 text-center xs:grid-cols-3 sm:px-6">
						<div class="flex flex-col space-y-1">
							<Label for="temperature" class="text-xs sm:text-sm">Temperature</Label>

							<input
								id="temperature"
								type="number"
								step=".01"
								bind:value={temperature}
								onchange={(e) => {
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
								class="rounded-md border border-transparent bg-[#F2F4F7] px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
							/>

							<Range bind:value={temperature} min=".01" max="1" step=".01" />
						</div>

						<div class="flex flex-col space-y-1">
							<Label for="max_tokens" class="text-xs sm:text-sm">Max tokens</Label>

							<input
								id="max_tokens"
								type="number"
								bind:value={maxTokens}
								onchange={(e) => {
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
								class="rounded-md border border-transparent bg-[#F2F4F7] px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
							/>

							<Range
								bind:value={maxTokens}
								min="1"
								max={$modelsAvailable.find((model) => model.id == selectedModel)?.context_length}
								step="1"
							/>
						</div>

						<div class="flex flex-col space-y-1">
							<Label for="top_p" class="text-xs sm:text-sm">Top-p</Label>

							<input
								id="top_p"
								type="number"
								step=".001"
								bind:value={topP}
								onchange={(e) => {
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
								class="rounded-md border border-transparent bg-[#F2F4F7] px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
							/>

							<Range bind:value={topP} min=".001" max="1" step=".001" />
						</div>

						<div class="flex flex-col space-y-1">
							<Label for="multiturn-enabled" class="text-xs sm:text-sm">Multi-turn chat</Label>

							<div
								class="flex items-center gap-2 rounded-md bg-[#F2F4F7] px-3 py-2 data-dark:bg-[#42464e]"
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

					<div class="grid grid-rows-[min-content_1fr] space-y-1 px-4 sm:px-6">
						<Label for="add_prompt" class="font-medium sm:text-sm">Customize prompt</Label>

						<div class="flex flex-wrap items-center gap-1">
							<span class="text-xxs text-[#999] sm:text-xs">Columns:</span>
							{#each usableColumns as column}
								<Button
									variant="ghost"
									class="h-[unset] rounded-sm border border-[#E5E5E5] bg-white px-1.5 py-0.5 !text-xxs text-[#666] hover:bg-black/[0.1] data-dark:border-[#333] data-dark:bg-white/[0.06] data-dark:text-white data-dark:hover:bg-white/[0.1] sm:py-1 sm:!text-xs"
									onclick={() => {
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
							class="h-96 rounded-md border border-transparent bg-[#F4F5FA] p-2 text-[14px] outline-none transition-colors placeholder:italic placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:text-black/60 disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5] data-dark:disabled:text-white/60"
						></textarea>
					</div>

					<div class="grid grid-rows-[min-content_1fr] space-y-1 px-4 sm:px-6">
						<Label for="system_prompt" class="font-medium sm:text-sm">
							Customize system prompt
						</Label>

						<textarea
							bind:value={systemPrompt}
							id="system_prompt"
							placeholder="Enter system prompt"
							class="h-96 rounded-md border border-transparent bg-[#F4F5FA] p-2 text-[14px] outline-none transition-colors placeholder:italic placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:text-black/60 disabled:opacity-50 data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5] data-dark:disabled:text-white/60"
						></textarea>
					</div>
				{:else}
					<div class="flex flex-col gap-1 px-4 sm:px-6">
						<span class="text-left text-xs font-medium text-black sm:text-sm">Source column</span>

						<Select.Root type="single" bind:value={selectedSourceColumn}>
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<Select.Trigger>
								{#snippet children()}
									<!-- <Button
										variant="outline-neutral"
										class="flex h-10 min-w-full items-center justify-between gap-8 rounded-md border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e] {selectedSourceColumn
											? ''
											: 'italic text-muted-foreground hover:text-muted-foreground'}"
									> -->
									<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
										{selectedSourceColumn || 'Select source column'}
									</span>
								{/snippet}
							</Select.Trigger>
							<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
								{#each usableColumns ?? [] as column}
									<Select.Item
										value={column.id}
										label={column.id}
										class="flex cursor-pointer justify-between gap-10"
									>
										{column.id}
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
				{/if}
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
					form="addColumnForm"
					loading={isLoading}
					disabled={isLoading}
					class="relative grow px-6"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
