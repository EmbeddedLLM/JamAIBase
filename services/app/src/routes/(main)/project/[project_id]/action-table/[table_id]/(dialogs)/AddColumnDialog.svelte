<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { modelsAvailable } from '$globalStore';
	import { insertAtCursor } from '$lib/utils';
	import { actionTableDTypes } from '$lib/constants';
	import logger from '$lib/logger';
	import type { ActionTableCol, ChatRequest } from '$lib/types';

	import ModelSelect from '$lib/components/preset/ModelSelect.svelte';
	import Range from '$lib/components/Range.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	const { PUBLIC_JAMAI_URL } = env;

	export let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean };
	let usableColumns: ActionTableCol[] = [];
	$: if ($page.data.table && $page.data.table.tableData && $page.data.table.tableData.cols) {
		usableColumns =
			($page.data.table.tableData.cols as ActionTableCol[])?.filter(
				(col) => col.id !== 'ID' && col.id !== 'Updated at'
			) ?? [];
	}

	let isLoading = false;
	let columnName = '';
	let selectedDatatype = '';
	let selectedModel = '';
	let temperature = '1';
	let maxTokens = '1000';
	let topP = '0.1';
	let prompt = '';
	let systemPrompt = '';

	async function handleAddColumn() {
		if (!columnName || !selectedDatatype) {
			return alert('Please fill in all fields');
		}

		if (isLoading) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/columns/add`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				id: $page.params.table_id,
				cols: [
					{
						id: columnName,
						dtype: selectedDatatype,
						vlen: 0,
						gen_config:
							isAddingColumn.type == 'output'
								? ({
										model: selectedModel,
										messages: [
											{
												role: 'system',
												content: systemPrompt
											},
											{
												role: 'user',
												content: prompt
											}
										],
										temperature: parseFloat(temperature),
										max_tokens: parseInt(maxTokens),
										top_p: parseFloat(topP)
									} satisfies Partial<ChatRequest>)
								: null
					}
				]
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_COLUMN_ADD', responseBody);
			alert('Failed to add column: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			invalidate('action-table:slug');
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
		style="min-width: {isAddingColumn.type == 'input' ? '35rem' : '65rem'}; {isAddingColumn.type ==
		'input'
			? ''
			: 'height: 90vh;'}"
	>
		<Dialog.Header>New {isAddingColumn.type} column</Dialog.Header>

		<div class="grow py-3 w-full overflow-auto">
			<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Column ID
				</span>

				<input
					type="text"
					bind:value={columnName}
					class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
				/>
			</div>

			<div class="flex flex-col gap-2 px-6 pl-8 py-4 w-full text-center">
				<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
					Data Type
				</span>

				<Select.Root>
					<Select.Trigger asChild let:builder>
						<Button
							builders={[builder]}
							variant="outline"
							class="flex items-center justify-between gap-8 pl-3 pr-2 h-10 min-w-full bg-white data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1]"
						>
							<span class="whitespace-nowrap line-clamp-1 font-normal text-left">
								{selectedDatatype ? selectedDatatype : 'Select Data Type'}
							</span>

							<ChevronDown class="h-4 w-4" />
						</Button>
					</Select.Trigger>
					<Select.Content side="bottom" class="max-h-96 overflow-y-auto">
						{#each actionTableDTypes as dType}
							<Select.Item
								on:click={() => (selectedDatatype = dType)}
								value={dType}
								label={dType}
								class="flex justify-between gap-10 cursor-pointer"
							>
								{dType}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			{#if isAddingColumn.type == 'output'}
				<div class="flex flex-col gap-1 px-6 pl-8 py-2">
					<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Models
					</span>

					<ModelSelect
						capabilityFilter="chat"
						sameWidth={true}
						bind:selectedModel
						buttonText={selectedModel || 'Select model'}
					/>
				</div>

				<div class="grid grid-cols-3 gap-4 px-6 pl-8 py-2 w-full text-center">
					<div class="flex flex-col gap-1">
						<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
							Temperature
						</span>

						<input
							type="number"
							step=".01"
							bind:value={temperature}
							on:blur={() =>
								(temperature =
									parseFloat(temperature) <= 0 ? '0.01' : parseFloat(temperature).toFixed(2))}
							class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						/>

						<Range bind:value={temperature} min=".01" max="1" step=".01" />
					</div>

					<div class="flex flex-col gap-1">
						<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
							Max tokens
						</span>

						<input
							type="number"
							bind:value={maxTokens}
							on:blur={() =>
								(maxTokens = parseInt(maxTokens) <= 0 ? '1' : parseInt(maxTokens).toString())}
							class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						/>

						<Range
							bind:value={maxTokens}
							min="1"
							max={$modelsAvailable.find((model) => model.id == selectedModel)?.contextLength ?? 0}
							step="1"
						/>
					</div>

					<div class="flex flex-col gap-1">
						<span class="py-2 font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
							Top-p
						</span>

						<input
							type="number"
							step=".001"
							bind:value={topP}
							on:blur={() => (topP = parseFloat(topP) <= 0 ? '0.001' : parseFloat(topP).toFixed(3))}
							class="px-3 py-2 w-44 text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
						/>

						<Range bind:value={topP} min=".001" max="1" step=".001" />
					</div>
				</div>

				<div class="grid grid-rows-[min-content_1fr] px-6 pl-8 py-4 overflow-auto">
					<span class="font-medium text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Customize prompt
					</span>

					<div class="flex items-center gap-1 mt-3">
						<span class="text-xs text-[#999]">Columns: </span>
						{#each usableColumns as column}
							<Button
								variant="ghost"
								class="px-1.5 py-1 h-[unset] text-xs bg-white data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1] border rounded-sm text-[#666] data-dark:text-white border-[#E5E5E5] data-dark:border-[#333]"
								on:click={() => {
									insertAtCursor(
										// @ts-ignore
										document.getElementById('add-prompt'),
										`\${${column.id}}`
									);
									// @ts-ignore
									prompt = document.getElementById('add-prompt')?.value ?? prompt;
									document.getElementById('add-prompt')?.focus();
								}}
							>
								{column.id}
							</Button>
						{/each}
					</div>

					<textarea
						bind:value={prompt}
						id="add-prompt"
						placeholder="Enter prompt"
						class="mt-1 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>
				</div>

				<div class="grid grid-rows-[min-content_1fr] px-6 pl-8 py-4 overflow-auto">
					<span class="font-medium text-sm text-[#999] data-dark:text-[#C9C9C9]">
						Customize system prompt
					</span>

					<textarea
						bind:value={systemPrompt}
						id="system-prompt"
						placeholder="Enter system prompt"
						class="mt-4 p-2 h-96 text-[14px] rounded-md disabled:text-black/60 data-dark:disabled:text-white/60 bg-[#F4F5FA] data-dark:bg-[#42464e] border border-[#DDD] data-dark:border-[#42464E] outline-none placeholder:italic placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
					/>
				</div>
			{/if}
		</div>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button
					variant="link"
					on:click={() => (isAddingColumn = { ...isAddingColumn, showDialog: false })}
					class="grow px-6"
				>
					Cancel
				</Button>
				<Button
					loading={isLoading}
					on:click={handleAddColumn}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
