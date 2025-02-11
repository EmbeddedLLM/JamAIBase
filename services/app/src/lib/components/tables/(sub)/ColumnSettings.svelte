<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { page } from '$app/stores';
	import { modelsAvailable } from '$globalStore';
	import { tableState } from '$lib/components/tables/tablesStore';
	import { insertAtCursor } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import SelectKnowledgeTableDialog from './SelectKnowledgeTableDialog.svelte';
	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import Range from '$lib/components/Range.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import * as Select from '$lib/components/ui/select';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import RowSearchIcon from '$lib/icons/RowSearchIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let showPromptTab = true;
	export let tableData: GenTable | undefined;
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	export let readonly = false;

	let showActual = $tableState.columnSettings.isOpen;

	let usableColumns: GenTableCol[] = [];
	$: if (tableData?.cols) {
		usableColumns =
			tableData.cols
				.slice(
					0,
					tableData.cols.findIndex((col) => col.id == $tableState.columnSettings.column?.id)
				)
				.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? [];
	}

	let selectedTab: 'prompt' | 'model_settings' = 'prompt';

	let isLoading = false;

	let selectedGenConfigObj: NonNullable<GenTableCol['gen_config']>['object'] | null = null;

	let selectedEmbedModel = '';
	let selectedSourceColumn = '';

	let isMultiturn = false;
	let isRAGEnabled = false;
	let editRAGk = '5';
	let editRAGFetchk = '20';
	let selectedRerankModel = '';

	let isSelectingKnowledgeTable = false;
	let selectedKnowledgeTables = '';

	let editPrompt = '';
	let editSystemPrompt = '';
	let selectedModel = '';
	let editTemperature = '1';
	let editMaxTokens = '1000';
	let editTopP = '0.1';

	$: if (showActual) resetValues();
	function resetValues() {
		selectedGenConfigObj = $tableState.columnSettings.column?.gen_config?.object ?? null;

		if (showPromptTab && selectedGenConfigObj !== 'gen_config.code') {
			selectedTab = 'prompt';
		} else {
			selectedTab = 'model_settings';
		}

		if ($tableState.columnSettings.column?.gen_config?.object === 'gen_config.llm') {
			const {
				gen_config: {
					prompt: prompt = '',
					system_prompt: system_prompt = '',
					model: model = '',
					temperature: temperature = 1,
					max_tokens: max_tokens = 1000,
					top_p: top_p = 0.1,

					multi_turn: multi_turn = false,
					rag_params
				}
			} = $tableState.columnSettings.column;

			editPrompt = prompt;
			editSystemPrompt = system_prompt;
			selectedModel = model;
			editTemperature = temperature.toString();
			editMaxTokens = max_tokens.toString();
			editTopP = top_p.toString();

			isMultiturn = multi_turn;
			isRAGEnabled = !!rag_params;
			editRAGk = rag_params?.k?.toString() ?? '5';
			selectedRerankModel = rag_params?.reranking_model ?? '';
			selectedKnowledgeTables = rag_params?.table_id ?? '';

			// reset irrelevant data
			selectedEmbedModel = '';
			selectedSourceColumn = '';
		} else {
			if ($tableState.columnSettings.column?.gen_config?.object === 'gen_config.embed') {
				selectedEmbedModel = $tableState.columnSettings.column?.gen_config?.embedding_model;
			}
			selectedSourceColumn = $tableState.columnSettings.column?.gen_config?.source_column ?? '';

			// reset irrelevant data
			editPrompt = '';
			editSystemPrompt = '';
			selectedModel = '';
			editTemperature = '1';
			editMaxTokens = '1000';
			editTopP = '0.1';

			isMultiturn = false;
			isRAGEnabled = false;
			editRAGk = '5';
			selectedRerankModel = '';
			selectedKnowledgeTables = '';
		}
	}

	function closeColumnSettings() {
		if ($tableState.columnSettings.column?.gen_config?.object === 'gen_config.llm') {
			const {
				object,
				prompt: prompt = '',
				system_prompt: system_prompt = '',
				model: model = '',
				temperature: temperature = 1,
				max_tokens: max_tokens = 1000,
				top_p: top_p = 0.1,
				multi_turn,
				rag_params
			} = $tableState.columnSettings.column.gen_config;
			if (
				selectedGenConfigObj !== object ||
				editPrompt !== prompt ||
				editSystemPrompt !== system_prompt ||
				selectedModel !== model ||
				editTemperature !== temperature.toString() ||
				editMaxTokens !== max_tokens.toString() ||
				editTopP !== top_p.toString() ||
				isMultiturn !== multi_turn ||
				isRAGEnabled !== !!rag_params ||
				editRAGk !== (rag_params?.k?.toString() ?? '5') ||
				selectedRerankModel !== (rag_params?.reranking_model ?? '') ||
				selectedKnowledgeTables !== (rag_params?.table_id ?? '')
			) {
				if (!readonly && !confirm('Discard unsaved changes?')) {
					return;
				}
			}
		} else if ($tableState.columnSettings.column?.gen_config?.object === 'gen_config.code') {
			const { object, source_column } = $tableState.columnSettings.column.gen_config;
			if (selectedGenConfigObj !== object || selectedSourceColumn !== source_column) {
				if (!readonly && !confirm('Discard unsaved changes?')) {
					return;
				}
			}
		}

		tableState.setColumnSettings({ ...$tableState.columnSettings, isOpen: false });
	}

	async function saveColumnSettings() {
		if (!$tableState.columnSettings.column || isLoading) return;
		if (isRAGEnabled && !selectedKnowledgeTables) {
			toast.error('Please select a knowledge table', { id: 'kt-select-req', duration: 2000 });
			return;
		}

		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/gen_config/update`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': $page.params.project_id
				},
				body: JSON.stringify({
					table_id: $page.params.table_id,
					column_map: {
						[$tableState.columnSettings.column.id]: (selectedGenConfigObj === 'gen_config.llm'
							? {
									object: 'gen_config.llm',
									model: selectedModel,
									system_prompt: editSystemPrompt,
									prompt: editPrompt || undefined,
									temperature: parseFloat(editTemperature),
									max_tokens: parseInt(editMaxTokens),
									top_p: parseFloat(editTopP),
									multi_turn: isMultiturn,
									rag_params: isRAGEnabled
										? {
												k: parseInt(editRAGk),
												// fetch_k: parseInt(editRAGFetchk),
												table_id: selectedKnowledgeTables,
												reranking_model: selectedRerankModel || null
											}
										: null
								}
							: {
									object: 'gen_config.code',
									source_column: selectedSourceColumn
								}) satisfies GenTableCol['gen_config']
					}
				})
			}
		);

		if (response.ok) {
			await refetchTable(false);
			tableState.setColumnSettings({ ...$tableState.columnSettings, isOpen: false });
		} else {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_SETTINGSUPDATE`), responseBody);
			toast.error('Failed to update column settings', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		isLoading = false;
	}
</script>

<svelte:document
	on:keydown={(e) => {
		if ($tableState.columnSettings.isOpen && e.key === 'Escape') {
			closeColumnSettings();
		}
	}}
/>

<!-- Column settings barrier dismissable -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
	class="absolute inset-0 z-30 {$tableState.columnSettings.isOpen
		? 'opacity-100 pointer-events-auto'
		: 'opacity-0 pointer-events-none'} transition-opacity duration-300"
	on:click={closeColumnSettings}
></div>

{#if $tableState.columnSettings.isOpen || showActual}
	<div
		data-testid="column-settings-area"
		inert={!$tableState.columnSettings.isOpen}
		on:animationstart={() => {
			if ($tableState.columnSettings.isOpen) {
				showActual = true;
			}
		}}
		on:animationend={() => {
			if (!$tableState.columnSettings.isOpen) {
				showActual = false;
			}
		}}
		class="absolute z-40 bottom-0 {$tableState.columnSettings.column?.gen_config
			? 'column-settings max-h-full'
			: 'h-16 max-h-16'} w-full bg-white data-dark:bg-[#0D0E11] {$tableState.columnSettings.isOpen
			? 'animate-in slide-in-from-bottom-full'
			: 'animate-out slide-out-to-bottom-full'} duration-300 ease-in-out"
	>
		<div class="relative flex flex-col h-full w-full">
			<div
				data-testid="column-settings-tabs"
				style="grid-template-columns: {showPromptTab && selectedGenConfigObj !== 'gen_config.code'
					? '70px'
					: ''} 140px;"
				class="flex-[0_0_auto] grid w-full font-medium text-sm bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333] overflow-hidden"
			>
				{#if showPromptTab && selectedGenConfigObj !== 'gen_config.code'}
					<button
						on:click={() => (selectedTab = 'prompt')}
						class="relative flex items-center justify-center px-3 py-3 min-h-10 max-h-10 transition-colors font-medium {$tableState
							.columnSettings.isOpen
							? selectedTab === 'prompt'
								? 'text-[#1D2939] data-dark:text-[#98A2B3]'
								: 'text-[#98A2B3] data-dark:text-[#1D2939]'
							: 'text-[#667085]'}"
					>
						Prompt
					</button>
				{/if}

				<button
					on:click={() => (selectedTab = 'model_settings')}
					class="relative flex items-center justify-center px-3 py-3 min-h-10 max-h-10 transition-colors font-medium {$tableState
						.columnSettings.isOpen
						? selectedTab === 'model_settings'
							? 'text-[#1D2939] data-dark:text-[#98A2B3]'
							: 'text-[#98A2B3] data-dark:text-[#1D2939]'
						: 'text-[#667085]'}"
				>
					Model Settings
				</button>
			</div>

			{#if selectedGenConfigObj}
				<div
					class="flex items-center justify-between px-3 py-1.5 w-full border-t border-b border-[#E4E7EC] data-dark:border-[#333]"
				>
					<div class="flex items-center gap-2 text-sm">
						<span
							style="background-color: {!$tableState.columnSettings.column?.gen_config
								? '#E9EDFA'
								: '#FFEAD5'}; color: {!$tableState.columnSettings.column?.gen_config
								? '#6686E7'
								: '#FD853A'};"
							class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
						>
							<span class="capitalize text-xs font-medium px-1">
								{!$tableState.columnSettings.column?.gen_config ? 'input' : 'output'}
							</span>
							<span
								class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
							>
								{$tableState.columnSettings.column?.dtype}
							</span>

							{#if $tableState.columnSettings.column?.gen_config?.object === 'gen_config.llm' && $tableState.columnSettings.column.gen_config.multi_turn}
								<hr class="ml-1 h-3 border-l border-[#FD853A]" />
								<div class="relative h-4 w-[18px]">
									<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
								</div>
							{/if}
						</span>

						<span class="line-clamp-2 break-all">
							{$tableState.columnSettings.column?.id}
						</span>
					</div>

					<div class="flex flex-col sm:flex-row items-end sm:items-center gap-2">
						{#if (tableType !== 'knowledge' || showPromptTab) && selectedGenConfigObj !== 'gen_config.code'}
							<div class="flex items-center gap-2 px-2.5 py-1 bg-[#F9FAFB] rounded-full">
								<Label
									for="multiturn-enabled"
									class="flex items-center gap-1 min-w-max text-[#475467]"
								>
									<MultiturnChatIcon class="h-6" />
									Multi-turn chat
								</Label>
								<Switch
									disabled={readonly}
									id="multiturn-enabled"
									name="multiturn-enabled"
									class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
									bind:checked={isMultiturn}
								/>
							</div>
						{/if}

						<!-- {#if showPromptTab}
							<div class="flex items-center gap-2 px-2.5 py-1.5 bg-[#F9FAFB] rounded-full">
								<Label
									for="gen-config-obj"
									class="flex items-center gap-1 min-w-max text-[#475467]"
								>
									{selectedGenConfigObj === 'gen_config.code' ? 'Code Config' : 'LLM Config'}
								</Label>
								<Switch
									disabled={readonly}
									id="gen-config-obj"
									name="gen-config-obj"
									class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
									checked={selectedGenConfigObj === 'gen_config.code'}
									on:click={() => {
										selectedGenConfigObj =
											selectedGenConfigObj === 'gen_config.code'
												? 'gen_config.llm'
												: 'gen_config.code';

										if (selectedGenConfigObj === 'gen_config.code' && selectedTab === 'prompt') {
											selectedTab = 'model_settings';
										} else {
											selectedTab = 'prompt';
										}
									}}
								/>
							</div>
						{/if} -->
					</div>
				</div>

				{#if (tableType === 'knowledge' && !showPromptTab) || selectedGenConfigObj === 'gen_config.code'}
					{@const fileOutput = selectedGenConfigObj === 'gen_config.code'}
					<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
						<div class="grid grid-rows-[min-content_1fr] py-5 overflow-auto">
							{#if !fileOutput}
								<div class="flex flex-col gap-1 px-6 sm:px-14 py-2">
									<span class="font-medium text-left text-xs sm:text-sm text-black">
										Embedding Model
									</span>

									<ModelSelect
										disabled
										capabilityFilter="embed"
										sameWidth={true}
										selectedModel={selectedEmbedModel}
										buttonText={($modelsAvailable.find((model) => model.id == selectedEmbedModel)
											?.name ??
											selectedEmbedModel) ||
											'Select model'}
										class="disabled:opacity-100 bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent [&>svg]:hidden"
									/>
								</div>
							{/if}

							<div class="flex flex-col gap-1 px-6 sm:px-14 py-2">
								<span class="font-medium text-left text-xs sm:text-sm text-black">
									Source Column
								</span>

								<Select.Root disabled={!fileOutput}>
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

											{#if fileOutput}
												<ChevronDown class="h-4 w-4" />
											{/if}
										</Button>
									</Select.Trigger>
									<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
										{#each tableData?.cols.filter((col) => !['ID', 'Updated at'].includes(col.id) && col.id !== $tableState.columnSettings.column?.id && col.dtype === 'str') ?? [] as column}
											<Select.Item
												on:click={() => (selectedSourceColumn = column.id)}
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
						</div>

						<div
							class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
						>
							<Button
								variant="link"
								on:click={() =>
									tableState.setColumnSettings({ ...$tableState.columnSettings, isOpen: false })}
							>
								Cancel
							</Button>
							{#if showPromptTab && !readonly}
								<Button
									loading={isLoading}
									disabled={isLoading}
									on:click={saveColumnSettings}
									class="rounded-full"
								>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{:else if selectedTab === 'prompt'}
					<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
						<div class="flex flex-col px-5 sm:px-3 py-3 overflow-auto">
							<span class="font-medium text-sm">Customize prompt</span>

							<div class="flex items-center gap-1 mt-1 flex-wrap">
								<span class="text-xxs sm:text-xs text-[#999]">Columns:</span>
								{#each usableColumns as column}
									<Button
										disabled={readonly}
										variant="ghost"
										class="px-1.5 py-0.5 sm:py-1 h-[unset] !text-xxs sm:!text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]"
										on:click={() => {
											insertAtCursor(
												// @ts-ignore
												document.getElementById('prompt'),
												`\${${column.id}}`
											);
											// @ts-ignore
											editPrompt = document.getElementById('prompt')?.value ?? editPrompt;
											document.getElementById('prompt')?.focus();
										}}
									>
										{column.id}
									</Button>
								{/each}
							</div>

							<textarea
								{readonly}
								id="prompt"
								placeholder="Enter prompt"
								bind:value={editPrompt}
								class="grow mt-1 p-2 h-1 min-h-64 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F2F4F7] data-dark:bg-[#42464e] border border-transparent data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors resize-none"
							></textarea>
						</div>

						<div
							class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
						>
							<Button variant="link" on:click={closeColumnSettings}>Cancel</Button>
							{#if !readonly}
								<Button
									loading={isLoading}
									disabled={isLoading}
									on:click={saveColumnSettings}
									class="rounded-full"
								>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{:else}
					<div class="grow grid grid-rows-[minmax(0,1fr)_65px] min-h-0">
						<div
							class="grid grid-cols-1 md:grid-cols-[4fr_2.5fr] mb-auto h-full overflow-auto md:overflow-visible"
						>
							<div
								class="flex flex-col border-r border-[#E5E5E5] data-dark:border-[#333] overflow-visible md:overflow-auto"
							>
								<div
									class="grid grid-rows-[min-content_1fr] gap-1 px-5 sm:px-3 py-3 sm:border-b border-[#E5E5E5] data-dark:border-[#333]"
								>
									<span class="font-medium text-sm">Customize system prompt</span>

									<textarea
										{readonly}
										id="system-prompt"
										placeholder="Enter system prompt"
										bind:value={editSystemPrompt}
										class="p-2 h-[25vh] text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F2F4F7] data-dark:bg-[#42464e] border border-transparent data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
									></textarea>
								</div>

								<div class="flex items-center gap-2 px-5 sm:px-3 py-3">
									<Switch
										disabled={readonly}
										id="rag-enabled"
										name="rag-enabled"
										class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
										bind:checked={isRAGEnabled}
									/>
									<Label for="rag-enabled" class="font-medium">Enable RAG</Label>
								</div>

								{#if isRAGEnabled}
									<div
										data-testid="column-settings-rag-settings"
										class="flex flex-col px-5 sm:px-3 pt-3 pb-5"
									>
										<span class="py-2 font-medium text-left">RAG Settings</span>

										<div
											class="grid grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] gap-4 w-full"
										>
											<div class="flex flex-col gap-1">
												<span class="font-medium text-left text-xs sm:text-sm text-black">k</span>

												<input
													{readonly}
													type="number"
													name="rag-k"
													bind:value={editRAGk}
													on:blur={() =>
														(editRAGk =
															parseInt(editRAGk) <= 0 ? '1' : parseInt(editRAGk).toString())}
													class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
												/>

												<Range
													disabled={readonly}
													bind:value={editRAGk}
													min="1"
													max="1024"
													step="1"
												/>
											</div>
										</div>

										<div class="mt-4 flex flex-col gap-1">
											<span
												class="font-medium text-left text-xs sm:text-sm text-black whitespace-nowrap"
											>
												Reranking Model
											</span>

											<ModelSelect
												disabled={readonly}
												capabilityFilter="rerank"
												sameWidth={true}
												selectCb={(model) =>
													(selectedRerankModel = selectedRerankModel === model ? '' : model)}
												selectedModel={selectedRerankModel}
												buttonText={($modelsAvailable.find(
													(model) => model.id == selectedRerankModel
												)?.name ??
													selectedRerankModel) ||
													'Select model (optional)'}
												class="h-10 bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent"
											/>
										</div>

										<div class="flex flex-col gap-1 mt-4">
											<span class="font-medium text-left text-xs sm:text-sm text-black">
												Knowledge tables
											</span>

											<div class="relative">
												<SearchIcon class="absolute top-1/2 left-3 -translate-y-1/2 h-4" />

												<input
													disabled
													value={selectedKnowledgeTables}
													name="rag-filter-query"
													placeholder="Select knowledge table"
													class="flex px-10 py-2 w-full text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent data-dark:border-[#42464E] ring-offset-background placeholder:text-muted-foreground placeholder:italic focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed transition-colors"
												/>

												<Button
													disabled={readonly}
													variant="ghost"
													title="Select knowledge table"
													on:click={() => (isSelectingKnowledgeTable = true)}
													class="absolute top-1/2 right-0 -translate-y-1/2 p-0 h-9 w-9 hover:bg-[#e1e2e6] rounded-md"
												>
													<RowSearchIcon class="w-4/5 h-4/5" />
												</Button>
											</div>
										</div>
									</div>
								{/if}
							</div>

							<hr class="block sm:hidden mt-8 border-r border-[#E5E5E5] data-dark:border-[#333]" />

							<div class="px-5 sm:px-3 py-3 flex flex-col gap-4 overflow-visible md:overflow-auto">
								<h6 class="font-medium">Settings</h6>

								<div class="flex flex-col gap-1">
									<span class="font-medium text-left text-xs sm:text-sm text-block">Model</span>

									<ModelSelect
										showCapabilities
										disabled={readonly}
										capabilityFilter="chat"
										{selectedModel}
										selectCb={(model) => {
											selectedModel = model;

											const modelDetails = $modelsAvailable.find((val) => val.id == model);
											if (modelDetails && parseInt(editMaxTokens) > modelDetails.context_length) {
												editMaxTokens = modelDetails.context_length.toString();
											}
										}}
										buttonText={($modelsAvailable.find((model) => model.id == selectedModel)
											?.name ??
											selectedModel) ||
											'Select model'}
										class="w-full bg-[#F2F4F7] data-dark:bg-[#42464e] hover:bg-[#e1e2e6] border-transparent"
									/>
								</div>

								<div class="grid grid-cols-[repeat(auto-fill,_minmax(300px,_1fr))] gap-4">
									<div class="flex flex-col gap-1">
										<span class="font-medium text-left text-xs sm:text-sm text-black">
											Temperature
										</span>

										<input
											{readonly}
											type="number"
											name="temperature"
											step=".01"
											bind:value={editTemperature}
											on:change={(e) => {
												const value = parseFloat(e.currentTarget.value);

												if (isNaN(value)) {
													editTemperature = '1';
												} else if (value < 0.01) {
													editTemperature = '0.01';
												} else if (value > 1) {
													editTemperature = '1';
												} else {
													editTemperature = value.toFixed(2);
												}
											}}
											class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
										/>

										<Range
											disabled={readonly}
											bind:value={editTemperature}
											min=".01"
											max="1"
											step=".01"
										/>
									</div>

									<div class="flex flex-col gap-1">
										<span class="font-medium text-left text-xs sm:text-sm text-black">
											Max tokens
										</span>

										<input
											{readonly}
											type="number"
											name="max-tokens"
											bind:value={editMaxTokens}
											on:change={(e) => {
												const value = parseInt(e.currentTarget.value);
												const model = $modelsAvailable.find((model) => model.id == selectedModel);

												if (isNaN(value)) {
													editMaxTokens = '1';
												} else if (value < 1 || value > 1e20) {
													editMaxTokens = '1';
												} else if (model && value > model.context_length) {
													editMaxTokens = model.context_length.toString();
												} else {
													editMaxTokens = value.toString();
												}
											}}
											class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
										/>

										<Range
											disabled={readonly}
											bind:value={editMaxTokens}
											min="1"
											max={$modelsAvailable.find((model) => model.id == selectedModel)
												?.context_length}
											step="1"
										/>
									</div>

									<div class="flex flex-col gap-1">
										<span class="font-medium text-left text-xs sm:text-sm text-black">Top-p</span>

										<input
											{readonly}
											type="number"
											name="top-p"
											step=".001"
											bind:value={editTopP}
											on:change={(e) => {
												const value = parseFloat(e.currentTarget.value);

												if (isNaN(value)) {
													editTopP = '1';
												} else if (value < 0.01) {
													editTopP = '0.001';
												} else if (value > 1) {
													editTopP = '1';
												} else {
													editTopP = value.toFixed(3);
												}
											}}
											class="px-3 py-2 text-sm bg-[#F2F4F7] data-dark:bg-[#42464e] rounded-md border border-transparent data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
										/>

										<Range
											disabled={readonly}
											bind:value={editTopP}
											min=".001"
											max="1"
											step=".001"
										/>
									</div>
								</div>
							</div>
						</div>

						<div
							class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
						>
							<Button variant="link" on:click={closeColumnSettings}>Cancel</Button>
							{#if !readonly}
								<Button
									loading={isLoading}
									disabled={isLoading}
									on:click={saveColumnSettings}
									class="rounded-full"
								>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</div>

	{#if !readonly}
		<SelectKnowledgeTableDialog bind:isSelectingKnowledgeTable bind:selectedKnowledgeTables />
	{/if}
{/if}

<style>
	.column-settings {
		height: 100%;
	}

	@media (min-height: 800px) {
		.column-settings {
			height: calc(100% * 5 / 6);
		}
	}

	@media (min-height: 1000px) {
		.column-settings {
			height: calc(100% * 4 / 6);
		}
	}

	@media (min-height: 1200px) {
		.column-settings {
			height: 50%;
		}
	}
</style>
