<script lang="ts">
	import { page } from '$app/stores';
	import { invalidate } from '$app/navigation';
	import { modelsAvailable } from '$globalStore';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { insertAtCursor } from '$lib/utils';
	import logger from '$lib/logger';
	import type { ActionTableCol } from '$lib/types';

	import SelectKnowledgeTableDialog from '../../SelectKnowledgeTableDialog.svelte';
	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import Range from '$lib/components/Range.svelte';
	import { Button } from '$lib/components/ui/button';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import RowSearchIcon from '$lib/icons/RowSearchIcon.svelte';
	import MessageSquareIcon from '$lib/icons/MessageSquareIcon.svelte';

	export let isColumnSettingsOpen: { column: ActionTableCol | null; showMenu: boolean };
	export let isDeletingColumn: string | null;
	let usableColumns: ActionTableCol[] = [];
	$: if ($page.data.table && $page.data.table.tableData && $page.data.table.tableData.cols) {
		usableColumns =
			($page.data.table.tableData.cols as ActionTableCol[])
				?.slice(
					0,
					($page.data.table.tableData.cols as ActionTableCol[]).findIndex(
						(col) => col.id == isColumnSettingsOpen.column?.id
					)
				)
				?.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') ?? [];
	}

	let selectedTab: 'prompt' | 'model_settings' = 'prompt';

	let isLoading = false;

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
		if (isColumnSettingsOpen.column?.id != 'AI') {
			selectedTab = 'prompt';
		} else {
			selectedTab = 'model_settings';
		}

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

	async function saveColumnTitle(
		e: KeyboardEvent & { currentTarget: EventTarget & HTMLInputElement }
	) {
		if (!isColumnSettingsOpen.column) return;
		if (e.key === 'Enter') {
			const response = await fetch(`/api/v1/gen_tables/chat/columns/rename`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					table_id: $page.params.table_id,
					column_map: {
						[isColumnSettingsOpen.column.id]: e.currentTarget.value
					}
				})
			});

			if (response.ok) {
				isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false };
				invalidate('chat-table:slug');
			} else {
				const responseBody = await response.json();
				logger.error('CHATTBL_COLUMN_RENAME', responseBody);
				alert('Failed to rename column ' + (responseBody.message || JSON.stringify(responseBody)));
			}
		}
	}

	async function saveColumnSettings() {
		if (!isColumnSettingsOpen.column || isLoading) return;

		isLoading = true;

		const response = await fetch(`/api/v1/gen_tables/chat/gen_config/update`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				column_map: {
					[isColumnSettingsOpen.column.id]: {
						model: selectedModel,
						messages:
							isColumnSettingsOpen.column.id === 'AI'
								? [{ role: 'system', content: editSystemPrompt }]
								: [
										{ role: 'system', content: editSystemPrompt },
										{ role: 'user', content: editPrompt }
									],
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
		});

		if (response.ok) {
			isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false };
			invalidate('chat-table:slug');
		} else {
			const responseBody = await response.json();
			logger.error('CHATTBL_COLUMN_SETTINGSUPDATE ', responseBody);
			alert(
				'Failed to update column settings: ' +
					(responseBody.message || JSON.stringify(responseBody))
			);
		}

		isLoading = false;
	}
</script>

<svelte:document
	on:keydown={(e) => {
		if (isColumnSettingsOpen.showMenu && e.key === 'Escape') {
			isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false };
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
	on:click={() => (isColumnSettingsOpen = { ...isColumnSettingsOpen, showMenu: false })}
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
			style="grid-template-columns: 145px 185px;"
			class="absolute -top-12 grid font-medium text-sm bg-white data-dark:bg-[#0D0E11] border-t border-r border-[#E5E5E5] data-dark:border-[#333] rounded-tr-lg overflow-hidden"
		>
			<button
				on:click={() => {
					if (isColumnSettingsOpen.column?.id != 'AI') {
						selectedTab = 'prompt';
					}
				}}
				style={isColumnSettingsOpen.showMenu ? undefined : 'background-color: transparent;'}
				class="relative flex items-center {isColumnSettingsOpen.showMenu && selectedTab == 'prompt'
					? 'justify-between'
					: 'justify-center bg-[#F2F2F2] data-dark:bg-[#1E1E1E]'} pl-6 pr-4 py-3 min-h-12 border-r border-[#E5E5E5] data-dark:border-[#333] transition-colors"
			>
				<div class="flex items-center justify-center gap-2">
					<MessageSquareIcon class="h-4 w-4" />
					Prompt
				</div>
				{#if isColumnSettingsOpen.showMenu && selectedTab == 'prompt'}
					<ChevronDown class="h-4 w-4" />
				{/if}
			</button>

			<button
				on:click={() => (selectedTab = 'model_settings')}
				style={isColumnSettingsOpen.showMenu ? undefined : 'background-color: transparent;'}
				class="relative flex items-center {isColumnSettingsOpen.showMenu &&
				selectedTab == 'model_settings'
					? 'justify-between'
					: 'justify-center bg-[#F2F2F2] data-dark:bg-[#1E1E1E]'} px-4 py-3 min-h-12 transition-colors"
			>
				<div class="flex items-center justify-center gap-2">
					<TuneIcon class="h-[18px] w-[18px]" />
					Model Settings
				</div>
				{#if isColumnSettingsOpen.showMenu}
					<ChevronDown class="h-4 w-4" />
				{/if}
			</button>
		</div>

		<div
			class="relative flex items-center px-4 min-h-16 w-full bg-white data-dark:bg-[#0D0E11] border-t border-b border-[#E5E5E5] data-dark:border-[#333] overflow-x-auto"
		>
			<div class="absolute left-0 h-12 w-1.5 rounded-tr-md rounded-br-md bg-[#30A8FF]"></div>

			<div
				class="flex items-center gap-2 px-3 py-2.5 text-sm bg-white data-dark:bg-[#484C55] border border-[#E5E5E5] data-dark:border-[#333] rounded-[8px] shadow-[0px_0px_8px_0px] shadow-black/25"
			>
				<span
					style="background-color: {!isColumnSettingsOpen.column?.gen_config
						? '#CFE8FF'
						: '#FFE3CF'}; color: {!isColumnSettingsOpen.column?.gen_config
						? '#3A73B6'
						: '#B6843A'};"
					class="w-min px-1 py-0.5 capitalize text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
				>
					{!isColumnSettingsOpen.column?.gen_config ? 'input' : 'output'}
				</span>
				<input
					type="text"
					on:input={(e) =>
						e.currentTarget.setAttribute('size', `${e.currentTarget.value.length * 1.2}`)}
					on:keydown={saveColumnTitle}
					size={(isColumnSettingsOpen.column?.id.length ?? 0) * 1.2}
					value={isColumnSettingsOpen.column?.id}
					class="bg-transparent"
				/>
			</div>
		</div>

		{#if isColumnSettingsOpen.column?.gen_config}
			{#if selectedTab === 'prompt'}
				<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
					<div class="grid grid-rows-[min-content_1fr] px-6 py-5 overflow-auto">
						<span class="font-medium text-sm">Customize prompt</span>

						<div class="flex items-center gap-1 mt-3">
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
							class="mt-1 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						/>
					</div>

					<div
						class="flex items-center justify-end gap-2 px-6 py-3 bg-white data-dark:bg-[#0D0E11] border-t border-[#E5E5E5] data-dark:border-[#333]"
					>
						<Button
							variant="destructive"
							on:click={() => {
								if (isColumnSettingsOpen.column) {
									isDeletingColumn = isColumnSettingsOpen.column.id;
									isColumnSettingsOpen = { column: null, showMenu: false };
								}
							}}
							class="rounded-full"
						>
							Delete column
						</Button>
						<Button loading={isLoading} on:click={saveColumnSettings} class="rounded-full">
							Update
						</Button>
						<!-- <Button on:click={() => alert('generate column')} class="rounded-full">Generate</Button> -->
					</div>
				</div>
			{:else}
				<div style="grid-template-rows: minmax(0, 1fr) 65px;" class="grow grid min-h-0">
					<div style="grid-template-columns: 4fr 2fr;" class="grid mb-auto h-full overflow-auto">
						<div
							class="flex flex-col overflow-auto border-r border-[#E5E5E5] data-dark:border-[#333]"
						>
							<div
								class="grid grid-rows-[min-content_1fr] px-6 py-5 border-b border-[#E5E5E5] data-dark:border-[#333]"
							>
								<span class="font-medium text-sm">Customize system prompt</span>

								<textarea
									id="system-prompt"
									placeholder="Enter system prompt"
									bind:value={editSystemPrompt}
									class="mt-4 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
								/>
							</div>

							<div class="flex items-center gap-2 px-6 {isRAGEnabled ? 'pt-5' : 'pt-5 pb-10'}">
								<Checkbox bind:checked={isRAGEnabled} id="rag-enabled" class="h-5 w-5" />

								<label
									for="rag-enabled"
									class="py-2 text-left text-sm text-[#999] data-dark:text-[#C9C9C9] select-none"
								>
									RAG
								</label>
							</div>

							{#if isRAGEnabled}
								<div class="flex flex-col px-6 pb-5">
									<span class="py-2 font-medium text-left text-sm"> RAG Settings </span>

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
										<SearchIcon class="absolute top-1/2 left-3 -translate-y-1/2 h-6 w-6" />

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

						<div class="px-6 py-5 flex flex-col gap-4 overflow-auto">
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
									max={$modelsAvailable.find((model) => model.id == selectedModel)?.contextLength ??
										0}
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
						<Button
							variant="destructive"
							on:click={() => {
								if (isColumnSettingsOpen.column) {
									isDeletingColumn = isColumnSettingsOpen.column.id;
									isColumnSettingsOpen = { column: null, showMenu: false };
								}
							}}
							class="rounded-full"
						>
							Delete column
						</Button>
						<Button loading={isLoading} on:click={saveColumnSettings} class="rounded-full">
							Update
						</Button>
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>

<SelectKnowledgeTableDialog bind:isSelectingKnowledgeTable bind:selectedKnowledgeTables />
