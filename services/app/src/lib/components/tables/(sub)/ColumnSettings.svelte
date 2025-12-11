<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import isEqual from 'lodash/isEqual';
	import { Minus } from '@lucide/svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { modelsAvailable } from '$globalStore';
	import { getTableState } from '$lib/components/tables/tablesState.svelte';
	import {
		promptVariablePattern,
		pythonVariablePattern,
		reasoningEffortEnum
	} from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import HowToUseTab from './HowToUseTab.svelte';
	import SelectKnowledgeTableDialog from './SelectKnowledgeTableDialog.svelte';
	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import PromptEditor from '$lib/components/preset/PromptEditor.svelte';
	import Range from '$lib/components/Range.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import * as Select from '$lib/components/ui/select';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import RowSearchIcon from '$lib/icons/RowSearchIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';

	const tableState = getTableState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		showPromptTab?: boolean;
		tableData: GenTable | undefined;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
		readonly?: boolean;
	}

	let {
		tableType,
		showPromptTab = true,
		tableData,
		refetchTable,
		readonly = false
	}: Props = $props();

	let selectedGenConfig: NonNullable<GenTableCol['gen_config']> | null = $derived(
		tableState.columnSettings.column?.gen_config ?? null
	);
	let originalCol = $derived(
		tableData?.cols.find((col) => col.id === tableState.columnSettings.column?.id) ?? null
	);

	let promptEditor = $state<PromptEditor>();

	let showActual = $state(tableState.columnSettings.isOpen);

	let usableColumns: GenTableCol[] = $derived(
		tableData?.cols
			.slice(
				0,
				tableData.cols.findIndex((col) => col.id == tableState.columnSettings.column?.id)
			)
			.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? []
	);

	let selectedTab: 'prompt' | 'rag_settings' | 'how_to_use' = $state('prompt');
	let showModelSettings = $state(true);

	let isLoading = $state(false);

	let isSelectingKnowledgeTable = $state(false);

	const tabItems = $derived.by(() => {
		if (!selectedGenConfig?.object) return [];

		const tabs: { id: typeof selectedTab; title: string }[] = [];

		if (selectedGenConfig.object !== 'gen_config.python') {
			if (showPromptTab && selectedGenConfig.object !== 'gen_config.code') {
				tabs.push({ id: 'prompt', title: 'Prompt' });
			}

			tabs.push({
				id: 'rag_settings',
				title: selectedGenConfig.object === 'gen_config.embed' ? 'Model Settings' : 'RAG'
			});
		} else {
			tabs.push({ id: 'prompt', title: 'Code' });
		}

		if (['gen_config.llm', 'gen_config.python'].includes(selectedGenConfig.object)) {
			tabs.push({ id: 'how_to_use', title: 'How to use' });
		}

		return tabs;
	});

	let promptVarCounter = $derived.by(() => {
		const matches = [
			...(selectedGenConfig?.object === 'gen_config.python'
				? selectedGenConfig.python_code
				: selectedGenConfig?.object === 'gen_config.llm'
					? (selectedGenConfig?.prompt ?? '')
					: ''
			).matchAll(
				selectedGenConfig?.object === 'gen_config.python'
					? pythonVariablePattern
					: promptVariablePattern
			)
		];

		return matches.reduce((counts: Record<string, number>, match) => {
			const variable = match[1];
			counts[variable] = (counts[variable] || 0) + 1;
			return counts;
		}, {});
	});

	$effect(() => {
		if (showActual) resetValues();
	});

	function resetValues() {
		const promptTab = tabItems.find((tab) => tab.id === 'prompt');

		if (promptTab) {
			selectedTab = promptTab.id;
		} else if (tabItems[0]) {
			selectedTab = tabItems[0].id;
		} else {
			selectedTab = 'prompt';
		}
	}

	function closeColumnSettings() {
		if (!isEqual(tableState.columnSettings.column?.gen_config, originalCol?.gen_config)) {
			if (!readonly && !confirm('Discard unsaved changes?')) {
				return;
			}
		}

		tableState.setColumnSettings({ ...tableState.columnSettings, isOpen: false });
	}

	async function saveColumnSettings() {
		if (!tableState.columnSettings.column || isLoading) return;
		if (
			selectedGenConfig?.object === 'gen_config.llm' &&
			selectedGenConfig.rag_params &&
			!selectedGenConfig.rag_params.table_id
		) {
			toast.error('Please select a knowledge table', { id: 'kt-select-req', duration: 2000 });
			return;
		}

		isLoading = true;

		// Strip windows carriage return
		if (tableState.columnSettings.column.gen_config?.object === 'gen_config.python') {
			tableState.columnSettings.column.gen_config.python_code =
				tableState.columnSettings.column.gen_config.python_code.replaceAll('\r', '');
		}

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/gen_config`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				table_id: page.params.table_id,
				column_map: {
					[tableState.columnSettings.column.id]: tableState.columnSettings.column.gen_config
				}
			})
		});

		if (response.ok) {
			await refetchTable(false);
			tableState.setColumnSettings({ ...tableState.columnSettings, isOpen: false });
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

	let CodeEditor: any = $state();
	let codeEditorInstance: any = $state();
	onMount(async () => {
		const module = await import('$lib/components/preset/CodeEditor.svelte');
		CodeEditor = module.default;
	});
</script>

<svelte:document
	onkeydown={(e) => {
		if (tableState.columnSettings.isOpen && e.key === 'Escape') {
			closeColumnSettings();
		}
	}}
/>

<!-- Column settings barrier dismissable -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="absolute inset-0 z-30 {tableState.columnSettings.isOpen
		? 'pointer-events-auto opacity-100'
		: 'pointer-events-none opacity-0'} transition-opacity duration-300"
	onclick={closeColumnSettings}
></div>

{#if tableState.columnSettings.isOpen || showActual}
	<div
		data-testid="column-settings-area"
		inert={!tableState.columnSettings.isOpen}
		onanimationstart={() => {
			if (tableState.columnSettings.isOpen) {
				showActual = true;
			}
		}}
		onanimationend={() => {
			if (!tableState.columnSettings.isOpen) {
				showActual = false;
			}
		}}
		class="absolute bottom-0 z-40 px-4 py-3 {tableState.columnSettings.column?.gen_config
			? 'column-settings max-h-full'
			: 'h-16 max-h-16'} w-full {tableState.columnSettings.isOpen
			? 'animate-in slide-in-from-bottom-full'
			: 'animate-out slide-out-to-bottom-full'} duration-300 ease-in-out"
	>
		<div class="relative flex h-full w-full flex-col data-dark:bg-[#0D0E11]">
			<div
				data-testid="column-settings-tabs"
				style="grid-template-columns: repeat({tabItems.length}, max-content);"
				class="grid w-full flex-[0_0_auto] overflow-hidden rounded-t-lg border-t border-[#F2F4F7] bg-white text-sm font-medium data-dark:border-[#333] data-dark:bg-[#0D0E11]"
			>
				{#each tabItems as tab}
					<button
						onclick={() => (selectedTab = tab.id)}
						class="relative flex max-h-10 min-h-10 items-center justify-center gap-1 px-3 py-3 font-medium transition-colors {tableState
							.columnSettings.isOpen
							? selectedTab === tab.id
								? 'text-[#1D2939] data-dark:text-[#98A2B3]'
								: 'text-[#98A2B3] data-dark:text-[#1D2939]'
							: 'text-[#667085]'}"
					>
						{#if tab.id === 'rag_settings' && selectedGenConfig?.object === 'gen_config.llm'}
							RAG
							<span
								style="background-color: {selectedGenConfig.rag_params
									? '#ECFDF3'
									: '#FEF2F2'}; color: {selectedGenConfig.rag_params ? '#039855' : '#DC2626'};"
								class="rounded-md px-1 py-0.5 font-normal"
							>
								{selectedGenConfig.rag_params ? 'Enabled' : 'Disabled'}
							</span>
						{:else}
							{tab.title}
						{/if}
					</button>
				{/each}
			</div>

			{#if selectedGenConfig?.object}
				{#if selectedTab !== 'how_to_use'}
					<div
						class="flex w-full flex-col items-start justify-between gap-2 border-t border-[#F2F4F7] bg-white px-3 pb-1.5 pt-2 data-dark:border-[#333] sm:flex-row sm:items-center"
					>
						<div class="flex items-center gap-2 text-sm">
							<span
								style="background-color: {!tableState.columnSettings.column?.gen_config
									? '#7995E9'
									: '#FD853A'};"
								class:pr-1={tableState.columnSettings.column?.gen_config?.object !==
									'gen_config.llm' || !tableState.columnSettings.column?.gen_config.multi_turn}
								class="flex w-min select-none items-center whitespace-nowrap rounded-lg p-0.5 py-1"
							>
								<span class="px-1 text-xs font-medium capitalize text-white">
									{!tableState.columnSettings.column?.gen_config ? 'input' : 'output'}
								</span>
								<span
									style="color: {!tableState.columnSettings.column?.gen_config
										? '#7995E9'
										: '#FD853A'};"
									class="w-min select-none whitespace-nowrap rounded-md bg-white px-1 text-xs font-medium"
								>
									{tableState.columnSettings.column?.dtype}
								</span>

								{#if tableState.columnSettings.column?.gen_config?.object === 'gen_config.llm' && tableState.columnSettings.column.gen_config.multi_turn}
									<hr class="ml-1 h-3 border-l border-white" />
									<div class="relative h-4 w-[18px]">
										<MultiturnChatIcon class="absolute h-[18px] -translate-y-px text-white" />
									</div>
								{/if}
							</span>

							<span class="line-clamp-2 break-all">
								{tableState.columnSettings.column?.id}
							</span>
						</div>

						<div class="flex flex-col items-start gap-2 overflow-auto sm:flex-row sm:items-center">
							{#if (tableType !== 'knowledge' || showPromptTab) && selectedGenConfig.object === 'gen_config.llm'}
								<div class="flex items-center gap-2 rounded-lg bg-[#F9FAFB] px-2.5 py-2">
									<Label
										for="multiturn-enabled"
										class="flex min-w-max items-center gap-1 text-[#475467]"
									>
										<MultiturnChatIcon class="h-6" />
										Multi-turn chat
									</Label>
									<Switch
										disabled={readonly}
										id="multiturn-enabled"
										name="multiturn-enabled"
										class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
										bind:checked={selectedGenConfig.multi_turn}
									/>
								</div>

								<div class="">
									<ModelSelect
										showCapabilities
										disabled={readonly}
										capabilityFilter="chat"
										bind:selectedModel={selectedGenConfig.model!}
										selectCb={(model) => {
											const modelDetails = $modelsAvailable.find((val) => val.id == model);
											if (
												modelDetails &&
												(selectedGenConfig.max_tokens ?? 0) > modelDetails.context_length
											) {
												selectedGenConfig.max_tokens = modelDetails.context_length;
											}

											// Removes openai only tools for non-openai models
											if (!modelDetails?.id.startsWith('openai/')) {
												const filterTools = selectedGenConfig.tools?.filter(
													(tool) => !['web_search', 'code_interpreter'].includes(tool.type)
												);
												selectedGenConfig.tools = filterTools?.length === 0 ? null : filterTools;
											}
										}}
										class="w-64 border-transparent bg-[#F9FAFB] hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
									/>
								</div>
							{/if}

							<!-- {#if showPromptTab}
							<div class="flex items-center gap-2 px-2.5 py-1.5 bg-[#F2F4F7] rounded-full">
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
				{/if}

				{#if (tableType === 'knowledge' && !showPromptTab) || selectedGenConfig.object === 'gen_config.code'}
					<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grid min-h-0 grow bg-white">
						<div class="grid grid-rows-[min-content_1fr] overflow-auto pb-3 pt-1.5">
							{#if selectedGenConfig.object === 'gen_config.embed'}
								<div class="flex flex-col gap-1 px-4 py-2">
									<span class="text-left text-xs font-medium text-black sm:text-sm">
										Embedding Model
									</span>

									<ModelSelect
										disabled
										capabilityFilter="embed"
										selectedModel={selectedGenConfig.embedding_model}
										class="border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e] [&>svg]:hidden"
									/>
								</div>
							{/if}

							{#if selectedGenConfig.object === 'gen_config.embed' || selectedGenConfig.object === 'gen_config.code'}
								<div class="flex flex-col gap-1 px-4 py-2">
									<span class="text-left text-xs font-medium text-black sm:text-sm">
										Source Column
									</span>

									<Select.Root
										disabled={selectedGenConfig.object === 'gen_config.embed'}
										type="single"
										bind:value={selectedGenConfig.source_column}
									>
										<Select.Trigger
											showArrow={selectedGenConfig.object !== 'gen_config.embed'}
											class="flex h-10 min-w-full items-center justify-between gap-8 border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e] {selectedGenConfig.source_column
												? ''
												: 'italic text-muted-foreground hover:text-muted-foreground'}"
										>
											{#snippet children()}
												<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
													{selectedGenConfig.source_column || 'Select source column'}
												</span>
											{/snippet}
										</Select.Trigger>
										<Select.Content side="bottom" class="max-h-64 overflow-y-auto">
											{#each tableData?.cols.filter((col) => !['ID', 'Updated at'].includes(col.id) && col.id !== tableState.columnSettings.column?.id && col.dtype === 'str') ?? [] as column}
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
						</div>

						<div
							class="flex items-center justify-end gap-2 border-t border-[#E5E5E5] px-6 py-3 data-dark:border-[#333]"
						>
							<Button
								variant="link"
								onclick={() =>
									tableState.setColumnSettings({ ...tableState.columnSettings, isOpen: false })}
							>
								Cancel
							</Button>
							{#if showPromptTab && !readonly}
								<Button loading={isLoading} disabled={isLoading} onclick={saveColumnSettings}>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{:else if selectedTab === 'prompt'}
					<div
						style="grid-template-rows: minmax(0, 1fr) 65px;"
						class="grid min-h-0 grow rounded-b-xl bg-white"
					>
						<div
							class="grid grid-cols-1 transition-[grid-template-columns] duration-300 sm:grid-rows-[unset] {selectedGenConfig.object ===
							'gen_config.llm'
								? showModelSettings
									? 'sm:grid-cols-[minmax(0,8fr)_minmax(300px,8fr)]'
									: 'sm:grid-cols-[minmax(0,8fr)_minmax(150px,1fr)]'
								: ''} {selectedGenConfig.object === 'gen_config.python'
								? 'grid-rows-1'
								: 'grid-rows-[repeat(2,minmax(450px,1fr))]'} min-h-0 overflow-auto"
						>
							<div class="flex flex-col space-y-1 overflow-auto pb-3 pl-3 pr-3 pt-1.5 sm:pr-2">
								<div class="flex flex-wrap items-center gap-1">
									<span class="text-xxs text-[#98A2B3] sm:text-xs">Columns:</span>
									{#each [...usableColumns, ...(selectedGenConfig.object === 'gen_config.python' && originalCol ? [originalCol] : [])] as column}
										<Button
											disabled={readonly}
											variant="ghost"
											class="h-[unset] gap-1 rounded-lg border border-[#E4E7EC] bg-white px-1.5 py-0.5 !text-[10px] font-normal hover:bg-black/[0.1] data-dark:border-[#333] data-dark:bg-white/[0.06] data-dark:hover:bg-white/[0.1] sm:py-1 sm:!text-xs {column.gen_config
												? '!text-[#FD853A]'
												: '!text-[#7995E9]'}"
											onclick={() => {
												if (selectedGenConfig.object === 'gen_config.python') {
													codeEditorInstance.insertText(`row["${column.id}"]`);
												} else {
													promptEditor?.insertTextAtCursor(`\${${column.id}}`);
												}
											}}
										>
											{column.id}

											<span
												class="flex aspect-square h-4 w-auto items-center justify-center rounded-md bg-[#E4E7EC] text-[10px] text-[#344054] sm:text-xs"
											>
												{promptVarCounter[column.id] || 0}
											</span>
										</Button>
									{/each}
								</div>

								{#if selectedGenConfig.object === 'gen_config.llm'}
									<PromptEditor
										bind:this={promptEditor}
										bind:editorContent={
											() => {
												if (selectedGenConfig?.object === 'gen_config.llm') {
													return selectedGenConfig?.prompt ?? '';
												} else {
													return '';
												}
											},
											(v) => {
												if (selectedGenConfig?.object === 'gen_config.llm')
													selectedGenConfig.prompt = v;
											}
										}
										{usableColumns}
									/>
								{:else if selectedGenConfig.object === 'gen_config.python'}
									<CodeEditor
										bind:this={codeEditorInstance}
										bind:code={selectedGenConfig.python_code}
									/>
								{/if}
							</div>

							{#if selectedGenConfig.object === 'gen_config.llm'}
								<div
									class="mb-3 ml-3 mr-3 mt-0 flex flex-col rounded-md border border-[#F2F4F7] bg-[#F9FAFB] py-3 @container/model-settings sm:ml-2 sm:mt-9 sm:h-[unset]"
								>
									<button
										onclick={() => (showModelSettings = !showModelSettings)}
										class="pointer-events-none ml-3 flex items-center gap-2 text-sm text-[#475467] sm:pointer-events-auto"
									>
										<svg
											viewBox="0 0 5 8"
											fill="none"
											xmlns="http://www.w3.org/2000/svg"
											class:rotate-180={!showModelSettings}
											class="h-2.5 transition-transform"
										>
											<path d="M0 4L4.5 0.535898V7.4641L0 4Z" fill="#475467" />
										</svg>

										Model Settings
									</button>

									<div
										class:duration-0={!showModelSettings}
										class="h-1 grow overflow-auto px-3 pt-2 transition-opacity {showModelSettings
											? 'opacity-100'
											: 'opacity-100 sm:opacity-0'}"
									>
										<textarea
											{readonly}
											id="system-prompt"
											placeholder="Enter system prompt"
											bind:value={selectedGenConfig.system_prompt}
											class=" h-[25vh] w-full rounded-md border border-transparent bg-[#F2F4F7] p-2 text-[14px] outline-none transition-colors placeholder:italic placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:text-black/60 disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5] data-dark:disabled:text-white/60"
										></textarea>

										<div
											class="mt-4 grid grid-cols-1 gap-x-4 gap-y-5 @lg/model-settings:grid-cols-3 @lg/model-settings:gap-y-6"
										>
											<div class="flex flex-col space-y-1">
												<Label for="temperature" class="text-xs sm:text-sm">Temperature</Label>

												<input
													{readonly}
													type="number"
													id="temperature"
													name="temperature"
													step=".01"
													bind:value={selectedGenConfig.temperature}
													onchange={(e) => {
														const value = parseFloat(e.currentTarget.value);

														if (isNaN(value)) {
															selectedGenConfig.temperature = 1;
														} else if (value < 0.01) {
															selectedGenConfig.temperature = 0.01;
														} else if (value > 1) {
															selectedGenConfig.temperature = 1;
														} else {
															selectedGenConfig.temperature = Number(value.toFixed(2));
														}
													}}
													class="rounded-md border border-[#E3E3E3] bg-white px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
												/>

												<Range
													disabled={readonly}
													bind:value={selectedGenConfig.temperature}
													min=".01"
													max="1"
													step=".01"
												/>
											</div>

											<div class="flex flex-col space-y-1">
												<Label for="max-tokens" class="text-xs sm:text-sm">Max tokens</Label>

												<input
													{readonly}
													type="number"
													id="max-tokens"
													name="max-tokens"
													bind:value={selectedGenConfig.max_tokens}
													onchange={(e) => {
														const value = parseInt(e.currentTarget.value);
														const model = $modelsAvailable.find(
															(model) => model.id == selectedGenConfig.model
														);

														if (isNaN(value)) {
															selectedGenConfig.max_tokens = 1;
														} else if (value < 1 || value > 1e20) {
															selectedGenConfig.max_tokens = 1;
														} else if (model && value > model.context_length) {
															selectedGenConfig.max_tokens = model.context_length;
														} else {
															selectedGenConfig.max_tokens = value;
														}
													}}
													class="rounded-md border border-[#E3E3E3] bg-white px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
												/>

												<Range
													disabled={readonly}
													bind:value={selectedGenConfig.max_tokens}
													min="1"
													max={$modelsAvailable.find((model) => model.id == selectedGenConfig.model)
														?.context_length}
													step="1"
												/>
											</div>

											<div class="flex flex-col space-y-1">
												<Label for="top-p" class="text-xs sm:text-sm">Top-p</Label>

												<input
													{readonly}
													type="number"
													id="top-p"
													name="top-p"
													step=".001"
													bind:value={selectedGenConfig.top_p}
													onchange={(e) => {
														const value = parseFloat(e.currentTarget.value);

														if (isNaN(value)) {
															selectedGenConfig.top_p = 1;
														} else if (value < 0.01) {
															selectedGenConfig.top_p = 0.001;
														} else if (value > 1) {
															selectedGenConfig.top_p = 1;
														} else {
															selectedGenConfig.top_p = Number(value.toFixed(3));
														}
													}}
													class="rounded-md border border-[#E3E3E3] bg-white px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
												/>

												<Range
													disabled={readonly}
													bind:value={selectedGenConfig.top_p}
													min=".001"
													max="1"
													step=".001"
												/>
											</div>

											{#if $modelsAvailable
												.find((val) => val.id == selectedGenConfig.model)
												?.capabilities.includes('reasoning')}
												<div class="flex flex-col space-y-1">
													<Label class="text-xs sm:text-sm">Reasoning effort</Label>

													<Select.Root
														allowDeselect
														type="single"
														bind:value={
															() => selectedGenConfig.reasoning_effort ?? '',
															(v) => (selectedGenConfig.reasoning_effort = v || null)
														}
													>
														<Select.Trigger
															title="Reasoning effort"
															class="mb-1 flex h-10 min-w-full items-center justify-between gap-8 border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] data-dark:bg-[#42464e]"
														>
															{#snippet children()}
																<span
																	class="line-clamp-1 w-full whitespace-nowrap text-left font-normal capitalize"
																>
																	{selectedGenConfig.reasoning_effort ?? 'Default'}
																</span>
															{/snippet}
														</Select.Trigger>
														<Select.Content
															data-testid="org-plan-select-list"
															class="max-h-64 overflow-y-auto"
														>
															{#each reasoningEffortEnum as reasoningEffort}
																<Select.Item
																	value={reasoningEffort}
																	class="flex cursor-pointer justify-between gap-10 capitalize"
																>
																	{reasoningEffort}
																</Select.Item>
															{/each}
														</Select.Content>
													</Select.Root>
												</div>
											{/if}

											{#if selectedGenConfig.model?.startsWith('openai/')}
												<div class="flex flex-col gap-2 space-y-1">
													<Label class="text-xs sm:text-sm">OpenAI Tools</Label>

													<div class="flex items-center gap-2 pl-1">
														<Checkbox
															disabled={readonly}
															id="openai-tool-websearch"
															name="openai-tool-websearch"
															class="[&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[1px]"
															bind:checked={
																() =>
																	!!selectedGenConfig.tools?.find(
																		(tool) => tool.type === 'web_search'
																	),
																() => {
																	if (
																		selectedGenConfig.tools?.find(
																			(tool) => tool.type === 'web_search'
																		)
																	) {
																		const filterTools = selectedGenConfig.tools.filter(
																			(tool) => tool.type !== 'web_search'
																		);
																		selectedGenConfig.tools =
																			filterTools.length === 0 ? null : filterTools;
																	} else {
																		selectedGenConfig.tools = [
																			...(selectedGenConfig.tools ?? []),
																			{ type: 'web_search' }
																		];
																	}
																}
															}
														/>

														<Label for="openai-tool-websearch">Web Search</Label>
													</div>

													<div class="flex items-center gap-2 pl-1">
														<Checkbox
															disabled={readonly}
															id="openai-tool-codeinterpreter"
															name="openai-tool-codeinterpreter"
															class="[&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[1px]"
															bind:checked={
																() =>
																	!!selectedGenConfig.tools?.find(
																		(tool) => tool.type === 'code_interpreter'
																	),
																() => {
																	if (
																		selectedGenConfig.tools?.find(
																			(tool) => tool.type === 'code_interpreter'
																		)
																	) {
																		const filterTools = selectedGenConfig.tools.filter(
																			(tool) => tool.type !== 'code_interpreter'
																		);
																		selectedGenConfig.tools =
																			filterTools.length === 0 ? null : filterTools;
																	} else {
																		selectedGenConfig.tools = [
																			...(selectedGenConfig.tools ?? []),
																			{ type: 'code_interpreter' }
																		];
																	}
																}
															}
														/>

														<Label for="openai-tool-codeinterpreter">Code Interpreter</Label>
													</div>
												</div>
											{/if}
										</div>
									</div>
								</div>
							{/if}
						</div>

						<div
							class="flex items-center justify-end gap-2 border-t border-[#E5E5E5] px-6 py-3 data-dark:border-[#333]"
						>
							<Button variant="link" onclick={closeColumnSettings}>Cancel</Button>
							{#if !readonly}
								<Button loading={isLoading} disabled={isLoading} onclick={saveColumnSettings}>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{:else if selectedTab === 'how_to_use'}
					<div class="grid min-h-0 grow grid-rows-[minmax(0,1fr)_65px] rounded-b-xl bg-white">
						<HowToUseTab {selectedGenConfig} />

						<div
							class="flex items-center justify-end gap-2 border-t border-[#E5E5E5] px-6 py-3 data-dark:border-[#333]"
						>
							<Button variant="link" onclick={closeColumnSettings}>Cancel</Button>
							{#if !readonly}
								<Button loading={isLoading} disabled={isLoading} onclick={saveColumnSettings}>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{:else if selectedGenConfig.object === 'gen_config.llm'}
					<div class="grid min-h-0 grow grid-rows-[minmax(0,1fr)_65px] rounded-b-xl bg-white">
						<div
							class="mb-auto grid h-full grid-cols-1 gap-3 overflow-auto md:grid-cols-[2.5fr_4fr] md:overflow-visible"
						>
							<div
								class="mb-3 ml-3 mr-3 flex flex-col overflow-visible rounded-xl border border-[#F2F4F7] bg-[#F9FAFB] p-3 data-dark:border-[#333] sm:mr-0 md:overflow-auto"
							>
								<p class="text-sm font-medium text-[#1D2939]">RAG Settings</p>

								<div class="mt-4 flex items-start justify-between gap-2 pl-1">
									<div class="flex flex-col gap-1">
										<Label for="rag-enabled" class="text-[#1D2939]">Enable RAG</Label>

										<p class="text-sm text-[#667085]">
											Model will retrieve relevant context from Knowledge Table for accurate
											response
										</p>
									</div>

									<Switch
										disabled={readonly}
										id="rag-enabled"
										name="rag-enabled"
										class=""
										bind:checked={
											() => !!selectedGenConfig.rag_params,
											(v) => {
												if (v) {
													selectedGenConfig.rag_params = {
														table_id: '',
														k: 1,
														reranking_model: null
													};
												} else {
													selectedGenConfig.rag_params = null;
												}
											}
										}
									/>
								</div>

								<div class="mt-4 flex items-start justify-between gap-2 pl-1">
									<div class="flex flex-col gap-1">
										<Label for="rag-inline-citations" class="text-[#1D2939]">
											Generate inline citations
										</Label>

										<p class="text-sm text-[#667085]">
											Model will cite its sources [1] as it writes
										</p>
									</div>

									<Switch
										disabled={readonly || !selectedGenConfig.rag_params}
										id="rag-inline-citations"
										name="rag-inline-citations"
										bind:checked={
											() => selectedGenConfig.rag_params?.inline_citations ?? false,
											(v) => {
												if (selectedGenConfig.rag_params) {
													selectedGenConfig.rag_params.inline_citations = v;
												}
											}
										}
									/>
								</div>

								<hr class="mt-4 border-[#E4E7EC]" />

								<div class="mt-4 flex flex-col pl-1">
									<div class="flex items-start justify-between gap-2">
										<div class="flex flex-col gap-1">
											<Label for="rag-k" class="text-[#1D2939]">k</Label>

											<p class="text-sm text-[#667085]">Number of chunks or documents in context</p>
										</div>

										<input
											{readonly}
											disabled={!selectedGenConfig.rag_params}
											type="number"
											id="rag-k"
											name="rag-k"
											bind:value={
												() => selectedGenConfig.rag_params?.k ?? 1,
												(v) => {
													if (selectedGenConfig.rag_params) {
														selectedGenConfig.rag_params.k = v;
													}
												}
											}
											onblur={() => {
												if (selectedGenConfig.rag_params) {
													selectedGenConfig.rag_params.k =
														//@ts-ignore
														parseInt(selectedGenConfig.rag_params.k) <= 0
															? 1
															: //@ts-ignore
																parseInt(selectedGenConfig.rag_params.k);
												}
											}}
											class="w-16 rounded-md border border-transparent bg-[#F2F4F7] px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
										/>
									</div>

									<Range
										disabled={readonly || !selectedGenConfig.rag_params}
										bind:value={
											() => selectedGenConfig.rag_params?.k ?? 0,
											(v) => {
												if (selectedGenConfig.rag_params) {
													selectedGenConfig.rag_params.k = v;
												}
											}
										}
										min="1"
										max="1024"
										step="1"
									/>
								</div>

								<div class="mt-4 flex flex-col pl-1">
									<Label class="text-[#1D2939]">Reranking Model</Label>

									<p class="mb-2 mt-1 text-sm text-[#667085]">
										Model to reorder retrieved chunks or documents based on relevance
									</p>

									<ModelSelect
										disabled={readonly || !selectedGenConfig.rag_params}
										capabilityFilter="rerank"
										allowDeselect
										bind:selectedModel={
											() => selectedGenConfig.rag_params?.reranking_model ?? '',
											(v) => {
												if (selectedGenConfig.rag_params) {
													selectedGenConfig.rag_params.reranking_model = v;
												}
											}
										}
										class="h-10 border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] disabled:hover:bg-[#F2F4F7] data-dark:bg-[#42464e]"
									/>
								</div>
							</div>

							<div
								class="mb-3 ml-3 mr-3 flex flex-col overflow-visible rounded-xl border border-[#F2F4F7] bg-[#F9FAFB] p-3 data-dark:border-[#333] sm:ml-0 md:overflow-auto"
							>
								<p class="text-sm text-[#1D2939]">Search Knowledge Table</p>

								<div class="relative mt-3">
									<SearchIcon class="absolute left-3 top-1/2 h-4 -translate-y-1/2 text-[#667085]" />

									<input
										disabled
										value={selectedGenConfig.rag_params?.table_id}
										name="rag-filter-query"
										placeholder="Select knowledge table"
										class="flex w-full rounded-md border border-transparent bg-[#F2F4F7] px-10 py-2 text-sm ring-offset-background transition-colors placeholder:italic placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
									/>

									<Button
										disabled={readonly || !selectedGenConfig.rag_params}
										variant="ghost"
										title="Select knowledge table"
										onclick={() => (isSelectingKnowledgeTable = true)}
										class="absolute right-0 top-1/2 h-9 w-9 -translate-y-1/2 rounded-md p-0 hover:bg-[#e1e2e6]"
									>
										<RowSearchIcon class="h-4/5 w-4/5" />
									</Button>
								</div>

								<div class="mt-2.5 flex flex-col">
									<div
										class="rounded-t-xl border border-b-0 border-[#F2F4F7] bg-white p-2 text-sm text-[#667085]"
									>
										Selected knowledge table ({selectedGenConfig.rag_params?.table_id ? '1' : '0'})
									</div>

									{#if selectedGenConfig.rag_params?.table_id}
										<div
											class="items flex items-center gap-2 border border-[#F2F4F7] bg-white p-2 text-sm text-[#475467] last:rounded-b-xl"
										>
											<button
												onclick={() => {
													if (selectedGenConfig.rag_params) {
														selectedGenConfig.rag_params.table_id = '';
													}
												}}
												class="flex h-[18px] w-[18px] items-center justify-center rounded-sm bg-[#F04438] text-white"
											>
												<Minus class="w-4" />
											</button>

											{selectedGenConfig.rag_params?.table_id}
										</div>
									{:else}
										<div
											class="flex justify-center border border-[#F2F4F7] bg-white p-2 text-sm text-[#475467] last:rounded-b-xl"
										>
											No knowledge table selected
										</div>
									{/if}
								</div>
							</div>
						</div>

						<div
							class="flex items-center justify-end gap-2 border-t border-[#E5E5E5] px-6 py-3 data-dark:border-[#333]"
						>
							<Button variant="link" onclick={closeColumnSettings}>Cancel</Button>
							{#if !readonly}
								<Button loading={isLoading} disabled={isLoading} onclick={saveColumnSettings}>
									Update
								</Button>
							{/if}
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</div>

	{#if !readonly && selectedGenConfig?.object === 'gen_config.llm'}
		<SelectKnowledgeTableDialog
			bind:isSelectingKnowledgeTable
			bind:selectedKnowledgeTables={
				() => selectedGenConfig.rag_params?.table_id ?? '',
				(v) => {
					if (selectedGenConfig.rag_params) {
						selectedGenConfig.rag_params.table_id = v;
					}
				}
			}
		/>
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
