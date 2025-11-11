<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/state';
	import { getTableState } from '../tablesState.svelte';
	import {
		columnIDPattern,
		genTableColDTypes,
		genTableColTypes,
		genTableDTypes,
		jamaiApiVersion
	} from '$lib/constants';
	import logger from '$lib/logger';
	import type { GenTable, GenTableCol } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	const tableState = getTableState();

	let {
		tableType,
		tableData,
		refetchTable
	}: {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	} = $props();

	let colIDPaddingWidth = $state(62);
	let colIDInputWidth = $state(235);

	let columnName = $state('');
	let colType = $state<keyof typeof genTableColTypes>('Input');
	let dType = $state('str');

	let isLoading = $state(false);

	async function handleAddColumn() {
		if (!columnName) {
			return toast.error('Column name cannot be empty', { id: 'col-id-req' });
		}

		if (!columnIDPattern.test(columnName))
			return toast.error(
				'Column name must have at least 1 character and up to 46 characters, start with an alphabet or number, and end with an alphabet or number or these symbols: .?!()-. Characters in the middle can include space and these symbols: .?!@#$%^&*_()-.',
				{ id: 'column-name-invalid' }
			);

		if (
			colType === 'Code Output' &&
			!tableData.cols
				.filter((col) => col.id !== 'ID' && col.id !== 'Updated at')
				.find((col) => col.dtype === 'str')
		) {
			return toast.error(`No valid source column found for new column`, {
				id: 'code-column-no-source'
			});
		}

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
							dtype: dType.replace('_code', ''),
							vlen: 0,
							gen_config: (colType !== 'Input'
								? colType === 'Code Output'
									? {
											object: 'gen_config.code',
											source_column:
												tableData.cols
													.filter((col) => col.id !== 'ID' && col.id !== 'Updated at')
													.findLast((col) => col.dtype === 'str')?.id ?? ''
										}
									: colType === 'Python Output'
										? {
												object: 'gen_config.python',
												python_code: `row["${columnName}"] = "<result here>"`
											}
										: {
												object: 'gen_config.llm'
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
			await refetchTable();
			tableState.addingCol = false;

			//TODO: Improve this, won't open if refetch doesn't resolve in time
			setTimeout(() => {
				const newCol = tableData.cols.find((col) => col.id === columnName);
				if (newCol && newCol.gen_config) {
					tableState.columnSettings = {
						isOpen: true,
						column: $state.snapshot(newCol)
					};
				}
				columnName = '';
			}, 500);

			colType = 'Input';
			dType = 'str';
		}

		isLoading = false;
	}

	let animationId: ReturnType<typeof requestAnimationFrame>;
	function handleResize() {
		if (animationId) {
			cancelAnimationFrame(animationId);
		}

		animationId = requestAnimationFrame(() => {
			const table = document.querySelector('[data-testid=table-area]')?.firstChild;
			if (table) (table as HTMLElement).scrollLeft = 999999;
		});
	}
</script>

<svelte:window
	onresize={handleResize}
	onkeydown={(e) => {
		if (e.key === 'Escape') {
			tableState.addingCol = false;
		}
	}}
/>

<div
	role="columnheader"
	class="pointer-events-none relative flex cursor-default items-center gap-1 border-[#E4E7EC] bg-[#30A8FF33] pl-2 pr-1 data-dark:border-[#333] [&:not(:last-child)]:border-r [&>*]:z-[-5]"
>
	<DropdownMenu.Root open>
		<DropdownMenu.Trigger></DropdownMenu.Trigger>

		<DropdownMenu.Content
			interactOutsideBehavior="ignore"
			escapeKeydownBehavior="ignore"
			trapFocus={false}
			align="start"
			sideOffset={16}
			alignOffset={-20}
			class="flex w-[20rem] flex-col gap-4 p-2"
		>
			<input
				type="text"
				bind:value={columnName}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						handleAddColumn();
					}
				}}
				style="left: {colIDPaddingWidth + 32}px; width: {colIDInputWidth}px;"
				class="pointer-events-auto absolute -top-[26px] h-[20px] rounded-[2px] border-0 bg-transparent text-sm outline outline-1 outline-[#4169e1] data-dark:outline-[#5b7ee5]"
			/>

			<div class="flex gap-1">
				<div class="flex w-full flex-col text-center">
					<Select.Root type="single" bind:value={colType}>
						<Select.Trigger
							class="flex h-[32px] min-w-full items-center justify-between gap-2 border border-[#E4E7EC] bg-white pl-3 pr-2 data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] sm:gap-8"
						>
							{#snippet children()}
								<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
									{colType || 'Select Column Type'}
								</span>
							{/snippet}
						</Select.Trigger>
						<Select.Content class="max-h-64 overflow-y-auto">
							{#each Object.keys(genTableColTypes) as colType}
								<Select.Item
									value={colType}
									label={colType}
									class="flex cursor-pointer justify-between gap-10"
								>
									{colType}
								</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>

				<div class="flex w-full flex-col text-center">
					<Select.Root type="single" bind:value={dType}>
						<Select.Trigger
							class="flex h-[32px] min-w-full items-center justify-between gap-2 border border-[#E4E7EC] bg-white pl-3 pr-2 data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] sm:gap-8"
						>
							{#snippet children()}
								<span class="line-clamp-1 whitespace-nowrap text-left font-normal">
									{genTableDTypes[dType] || 'Select Data Type'}
								</span>
							{/snippet}
						</Select.Trigger>
						<Select.Content class="max-h-64 overflow-y-auto">
							{#each genTableColDTypes[colType] as dType}
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
			</div>

			<div class="flex justify-end gap-2 overflow-x-auto overflow-y-hidden">
				<Button
					variant="ghost"
					type="button"
					disabled={isLoading}
					onclick={() => (tableState.addingCol = false)}
					class="h-[unset] bg-[#F2F4F7] py-1 text-[#475467] hover:bg-[#E4E7EC]"
				>
					Cancel
				</Button>
				<Button
					type="button"
					disabled={isLoading}
					loading={isLoading}
					onclick={handleAddColumn}
					class="relative h-[unset] py-1.5"
				>
					Add column
				</Button>
			</div>
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	<span
		bind:clientWidth={colIDPaddingWidth}
		style="background-color: {colType === 'Input' ? '#7995E9' : '#FD853A'};"
		class="mr-1 flex w-min select-none items-center whitespace-nowrap rounded-lg px-0.5 py-1 pr-1 text-xxs text-white sm:text-xs"
	>
		<span class="px-1 font-medium capitalize">
			{colType === 'Input' ? 'Input' : 'Output'}
		</span>
		<span
			style="color: {colType === 'Input' ? '#7995E9' : '#FD853A'};"
			class="w-min select-none whitespace-nowrap rounded-md bg-white px-1 font-medium"
		>
			{dType}
		</span>

		<!-- {#if column.gen_config?.object === 'gen_config.llm' && column.gen_config.multi_turn}
						<hr class="ml-1 h-3 border-l border-white" />
						<div class="relative h-4 w-[18px]">
							<MultiturnChatIcon class="absolute h-[18px] -translate-y-px text-white" />
						</div>
					{/if} -->
	</span>

	<!-- svelte-ignore a11y_autofocus -->
	<input
		type="text"
		bind:value={columnName}
		bind:clientWidth={colIDInputWidth}
		class="pointer-events-auto w-full rounded-[2px] border-0 bg-transparent opacity-0 outline outline-1 outline-[#4169e1] data-dark:outline-[#5b7ee5]"
	/>

	<!-- {#if tableState.renamingCol === column.id}
			<!-- svelte-ignore a11y_autofocus ->
			<input
				type="text"
				id="column-id-edit"
				value={column.id}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();

						handleSaveColumnTitle(e);
					} else if (e.key === 'Escape') {
						tableState.setRenamingCol(null);
					}
				}}
				onblur={() => setTimeout(() => tableState.setRenamingCol(null), 100)}
				class="pointer-events-auto w-full rounded-[2px] border-0 bg-transparent outline outline-1 outline-[#4169e1] data-dark:outline-[#5b7ee5]"
			/>
		{:else}
			<span
				class="w-full font-medium {column.id === 'ID' || column.id === 'Updated at'
					? 'text-[#98A2B3]'
					: 'text-[#666] data-dark:text-white'} line-clamp-1 break-all"
			>
				{column.id}
			</span>
		{/if} -->
</div>
