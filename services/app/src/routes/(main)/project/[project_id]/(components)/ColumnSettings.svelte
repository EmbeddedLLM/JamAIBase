<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { page } from '$app/stores';
	import { invalidate } from '$app/navigation';
	import { modelsAvailable } from '$globalStore';
	import { insertAtCursor } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTableCol } from '$lib/types';

	import SelectKnowledgeTableDialog from './SelectKnowledgeTableDialog.svelte';
	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import Range from '$lib/components/Range.svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import * as Select from '$lib/components/ui/select';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import RowSearchIcon from '$lib/icons/RowSearchIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean };
	export let showPromptTab = true;

	let usableColumns: GenTableCol[] = [];
	$: if ($page.data.table && $page.data.table.tableData && $page.data.table.tableData.cols) {
		usableColumns =
			($page.data.table.tableData.cols as GenTableCol[])
				?.slice(
					0,
					($page.data.table.tableData.cols as GenTableCol[]).findIndex(
						(col) => col.id == isColumnSettingsOpen.column?.id
					)
				)
				?.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? [];
	}

	let selectedTab: 'prompt' | 'model_settings' = 'prompt';

	let isLoading = false;

	let selectedEmbedModel = '';
	let selectedSourceColumn = '';

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

	$: if (isColumnSettingsOpen.showMenu) resetValues();
	function resetValues() {
		if (showPromptTab) {
			selectedTab = 'prompt';
		} else {
			selectedTab = 'model_settings';
		}

		selectedEmbedModel = isColumnSettingsOpen.column?.gen_config?.embedding_model ?? '';
		selectedSourceColumn = isColumnSettingsOpen.column?.gen_config?.source_column ?? '';

		editPrompt = isColumnSettingsOpen.column?.gen_config?.messages?.[1]?.content ?? '';
		editSystemPrompt = isColumnSettingsOpen.column?.gen_config?.messages?.[0]?.content ?? '';
		selectedModel = isColumnSettingsOpen.column?.gen_config?.model ?? '';
		editTemperature = isColumnSettingsOpen.column?.gen_config?.temperature?.toString() ?? '1';
		editMaxTokens = isColumnSettingsOpen.column?.gen_config?.max_tokens?.toString() ?? '1000';
		editTopP = isColumnSettingsOpen.column?.gen_config?.top_p?.toString() ?? '0.1';

		isRAGEnabled = !!isColumnSettingsOpen.column?.gen_config?.rag_params;
		editRAGk = isColumnSettingsOpen.column?.gen_config?.rag_params?.k?.toString() ?? '5';
		selectedRerankModel =
			isColumnSettingsOpen.column?.gen_config?.rag_params?.reranking_model ?? '';
		selectedKnowledgeTables = isColumnSettingsOpen.column?.gen_config?.rag_params?.table_id ?? '';
	}

	function closeColumnSettings() {
		const { messages, model, temperature, max_tokens, top_p, rag_params } =
			isColumnSettingsOpen.column?.gen_config ?? {};
		if (
			editPrompt !== (messages?.[1]?.content ?? '') ||
			editSystemPrompt !== (messages?.[0]?.content ?? '') ||
			selectedModel !== (model ?? '') ||
			editTemperature !== (temperature?.toString() ?? '1') ||
			editMaxTokens !== (max_tokens?.toString() ?? '1000') ||
			editTopP !== (top_p?.toString() ?? '0.1') ||
			isRAGEnabled !== !!rag_params ||
			editRAGk !== (rag_params?.k?.toString() ?? '5') ||
			selectedRerankModel !== (rag_params?.reranking_model ?? '') ||
			selectedKnowledgeTables !== (rag_params?.table_id ?? '')
		) {
			if (!confirm('Discard unsaved changes?')) {
				return;
			}
		}
		isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false };
	}

	async function saveColumnSettings() {
		if (!isColumnSettingsOpen.column || isLoading) return;

		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/gen_config/update`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					table_id: $page.params.table_id,
					column_map: {
						[isColumnSettingsOpen.column.id]: {
							model: selectedModel,
							messages: [
								{ role: 'system', content: editSystemPrompt },
								editPrompt ? { role: 'user', content: editPrompt } : undefined
							].filter((i) => i),
							temperature: parseFloat(editTemperature),
							max_tokens: parseInt(editMaxTokens),
							top_p: parseFloat(editTopP),
							rag_params: isRAGEnabled
								? {
										k: parseInt(editRAGk),
										// fetch_k: parseInt(editRAGFetchk),
										table_id: selectedKnowledgeTables,
										reranking_model: selectedRerankModel || null
									}
								: undefined
						}
					}
				})
			}
		);

		if (response.ok) {
			await invalidate(`${tableType}-table:slug`);
			isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false };
		} else {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_SETTINGSUPDATE`), responseBody);
			toast.error('Failed to update column settings', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
		}

		isLoading = false;
	}
</script>

<svelte:document
	on:keydown={(e) => {
		if (isColumnSettingsOpen.showMenu && e.key === 'Escape') {
			closeColumnSettings();
		}
	}}
/>

<!-- Column settings barrier dismissable -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
	class="absolute inset-0 z-30 bg-black/10 {isColumnSettingsOpen.showMenu
		? 'opacity-100 pointer-events-auto'
		: 'opacity-0 pointer-events-none'} transition-opacity duration-300"
	on:click={closeColumnSettings}
/>

<div
	inert={!isColumnSettingsOpen.showMenu}
	class="absolute z-40 top-full {isColumnSettingsOpen.column?.gen_config
		? 'h-1/2 max-h-[50%]'
		: 'h-16 max-h-16'} w-full bg-white data-dark:bg-[#0D0E11] transition-transform duration-300 {isColumnSettingsOpen.showMenu
		? '-translate-y-full'
		: 'translate-y-0'} ease-in-out"
>
	<div class="relative flex flex-col h-full w-full">
		<div
			style="grid-template-columns: {showPromptTab ? '70px' : ''} 140px;"
			class="flex-[0_0_auto] grid w-full font-medium text-sm bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333] overflow-hidden"
		>
			{#if showPromptTab}
				<button
					on:click={() => (selectedTab = 'prompt')}
					class="relative flex items-center justify-center px-3 py-3 min-h-10 max-h-10 transition-colors {isColumnSettingsOpen.showMenu
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
				class="relative flex items-center justify-center px-3 py-3 min-h-10 max-h-10 transition-colors {isColumnSettingsOpen.showMenu
					? selectedTab === 'model_settings'
						? 'text-[#1D2939] data-dark:text-[#98A2B3]'
						: 'text-[#98A2B3] data-dark:text-[#1D2939]'
					: 'text-[#667085]'}"
			>
				Model Settings
			</button>
		</div>

		<div
			class="relative flex items-center px-3 min-h-14 w-full bg-[#F2F4F7] data-dark:bg-[#0D0E11] border-t border-b border-[#E5E5E5] data-dark:border-[#333] overflow-x-auto"
		>
			<div class="absolute left-0 h-11 w-1 rounded-tr-full rounded-br-full bg-[#30A8FF]"></div>

			<div
				class="flex items-center gap-2 p-2 text-sm bg-white data-dark:bg-[#484C55] border border-[#E5E5E5] data-dark:border-[#333] rounded-[8px] shadow-[0px_1px_3px_0px] shadow-[#1018281A]"
			>
				<span
					style="background-color: {!isColumnSettingsOpen.column?.gen_config
						? '#E9EDFA'
						: '#FFEAD5'}; color: {!isColumnSettingsOpen.column?.gen_config
						? '#6686E7'
						: '#FD853A'};"
					class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
				>
					<span class="capitalize text-xs font-medium px-1">
						{!isColumnSettingsOpen.column?.gen_config ? 'input' : 'output'}
					</span>
					<span
						class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
					>
						{isColumnSettingsOpen.column?.dtype}
					</span>
				</span>

				<span>
					{isColumnSettingsOpen.column?.id}
				</span>
			</div>
		</div>

		{#if isColumnSettingsOpen.column?.gen_config}
			{#if selectedTab === 'prompt'}
				<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
					<div class="flex flex-col p-3 overflow-auto">
						<span class="font-medium text-sm">Customize prompt</span>

						<div class="flex items-center gap-1 mt-2">
							<span class="text-xs text-[#999]">Columns: </span>
							{#each usableColumns as column}
								<Button
									variant="ghost"
									class="px-1.5 py-1 h-[unset] text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]"
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
							id="prompt"
							placeholder="Enter prompt"
							bind:value={editPrompt}
							class="grow mt-1 p-2 h-1 min-h-48 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors resize-none"
						/>
					</div>

					<div
						class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
					>
						<Button variant="link" on:click={closeColumnSettings}>Cancel</Button>
						<Button
							loading={isLoading}
							disabled={isLoading}
							on:click={saveColumnSettings}
							class="rounded-full"
						>
							Update
						</Button>
					</div>
				</div>
			{:else if tableType === 'knowledge' && !showPromptTab}
				<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
					<div class="grid grid-rows-[min-content_1fr] px-6 py-5 overflow-auto">
						<div class="flex flex-col gap-1 px-6 pl-8 py-2">
							<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								Embedding Model
							</span>

							<ModelSelect
								disabled
								capabilityFilter="embed"
								sameWidth={true}
								selectedModel={selectedEmbedModel}
								buttonText={selectedEmbedModel || 'Select model'}
							/>
						</div>

						<div class="flex flex-col gap-1 px-6 pl-8 py-2">
							<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								Source Column
							</span>

							<Select.Root disabled>
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<Select.Trigger asChild let:builder>
									<Button
										builders={[builder]}
										variant="outline"
										class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
									>
										<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
											{selectedSourceColumn || 'Select Source Column'}
										</span>

										<ChevronDown class="h-4 w-4" />
									</Button>
								</Select.Trigger>
								<Select.Content side="bottom" class="max-h-96 overflow-y-auto">
									{#each $page.data.table.tableData.cols as column}
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
					</div>

					<!-- <div
						class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
					>
						<Button
							variant="link"
							on:click={() => (isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false })}
						>
							Cancel
						</Button>
						<Button loading={isLoading} on:click={saveColumnSettings} class="rounded-full">
							Update
						</Button>
					</div> -->
				</div>
			{:else}
				<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
					<div style="grid-template-columns: 4fr 2fr;" class="grid mb-auto h-full">
						<div
							class="flex flex-col overflow-auto border-r border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div
								class="grid grid-rows-[min-content_1fr] p-3 border-b border-[#E5E5E5] data-dark:border-[#333]"
							>
								<span class="font-medium text-sm">Customize system prompt</span>

								<textarea
									id="system-prompt"
									placeholder="Enter system prompt"
									bind:value={editSystemPrompt}
									class="mt-4 p-2 h-[25vh] text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
								/>
							</div>

							<div class="flex items-center gap-2 p-3">
								<Switch
									id="rag-enabled"
									class="h-[20px] w-[30px] [&>[data-switch-thumb]]:h-4 [&>[data-switch-thumb]]:data-[state=checked]:translate-x-2.5"
									bind:checked={isRAGEnabled}
								/>
								<Label for="rag-enabled" class="font-medium">Enable RAG</Label>
							</div>

							{#if isRAGEnabled}
								<div class="flex flex-col px-3 pb-5">
									<span class="py-2 font-medium text-left">RAG Settings</span>

									<div class="flex flex-col gap-4 w-full">
										<div class="flex flex-col gap-1 w-1/2">
											<span
												class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
											>
												k
											</span>

											<input
												type="number"
												bind:value={editRAGk}
												on:blur={() =>
													(editRAGk =
														parseInt(editRAGk) <= 0 ? '1' : parseInt(editRAGk).toString())}
												class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
											/>

											<Range bind:value={editRAGk} min="1" max="1024" step="1" />
										</div>

										<div class="flex flex-col gap-1">
											<span
												class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9] whitespace-nowrap"
											>
												Reranking Model
											</span>

											<ModelSelect
												capabilityFilter="rerank"
												sameWidth={true}
												bind:selectedModel={selectedRerankModel}
												buttonText={selectedRerankModel || 'Select model'}
												class="h-10"
											/>
										</div>
									</div>

									<span class="mt-4 py-2 text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
										Knowledge tables
									</span>

									<div class="relative">
										<SearchIcon class="absolute top-1/2 left-3 -translate-y-1/2 h-[18px]" />

										<input
											disabled
											value={selectedKnowledgeTables}
											name="rag-filter-query"
											placeholder="Select knowledge table"
											class="flex px-12 py-2 h-11 w-full rounded-lg border data-dark:border border-transparent data-dark:border-[#42464E] ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors bg-[#F4F5FA] data-dark:bg-transparent"
										/>

										<Button
											title="Select knowledge table"
											variant="ghost"
											on:click={() => (isSelectingKnowledgeTable = true)}
											class="absolute top-1/2 right-2 -translate-y-1/2 p-0 h-9 w-9"
										>
											<RowSearchIcon class="w-4/5 h-4/5" />
										</Button>
									</div>
								</div>
							{/if}
						</div>

						<div class="p-3 flex flex-col gap-4 overflow-auto">
							<h6 class="font-medium">Settings</h6>

							<div class="flex flex-col gap-1">
								<span
									class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
								>
									Model
								</span>

								<ModelSelect
									capabilityFilter="chat"
									sameWidth={false}
									bind:selectedModel
									buttonText={selectedModel || 'Select model'}
									class="w-full"
								/>
							</div>

							<div class="flex flex-col gap-1">
								<span
									class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
								>
									Temperature
								</span>

								<input
									type="number"
									step=".01"
									bind:value={editTemperature}
									on:blur={() =>
										(editTemperature =
											parseFloat(editTemperature) <= 0
												? '0.01'
												: parseFloat(editTemperature).toFixed(2))}
									class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
								/>

								<Range bind:value={editTemperature} min=".01" max="1" step=".01" />
							</div>

							<div class="flex flex-col gap-1">
								<span
									class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
								>
									Max tokens
								</span>

								<input
									type="number"
									bind:value={editMaxTokens}
									on:blur={() =>
										(editMaxTokens =
											parseInt(editMaxTokens) <= 0 ? '1' : parseInt(editMaxTokens).toString())}
									class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
								/>

								<Range
									bind:value={editMaxTokens}
									min="1"
									max={$modelsAvailable.find((model) => model.id == selectedModel)
										?.context_length ?? 0}
									step="1"
								/>
							</div>

							<div class="flex flex-col gap-1">
								<span
									class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]"
								>
									Top-p
								</span>

								<input
									type="number"
									step=".001"
									bind:value={editTopP}
									on:blur={() =>
										(editTopP =
											parseFloat(editTopP) <= 0 ? '0.001' : parseFloat(editTopP).toFixed(3))}
									class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
								/>

								<Range bind:value={editTopP} min=".001" max="1" step=".001" />
							</div>
						</div>
					</div>

					<div
						class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
					>
						<Button variant="link" on:click={closeColumnSettings}>Cancel</Button>
						<Button
							loading={isLoading}
							disabled={isLoading}
							on:click={saveColumnSettings}
							class="rounded-full"
						>
							Update
						</Button>
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>

<SelectKnowledgeTableDialog bind:isSelectingKnowledgeTable bind:selectedKnowledgeTables />
