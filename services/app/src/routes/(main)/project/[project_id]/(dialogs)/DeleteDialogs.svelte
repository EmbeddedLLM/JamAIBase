<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/state';
	import { getTableState, getTableRowsState } from '$lib/components/tables/tablesState.svelte';
	import logger from '$lib/logger';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	const tableState = getTableState();
	const tableRowsState = getTableRowsState();

	interface Props {
		tableType: 'action' | 'knowledge' | 'chat';
		isDeletingRow: string[] | null;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	}

	let { tableType, isDeletingRow = $bindable(), refetchTable }: Props = $props();

	let isLoading = $state(false);

	async function handleDeleteColumn() {
		if (isLoading || !tableState.deletingCol) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/columns/drop`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
				},
				body: JSON.stringify({
					table_id: page.params.table_id,
					column_names: [tableState.deletingCol]
				})
			}
		);
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_DEL`), responseBody);
			toast.error('Failed to delete column', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		} else {
			await refetchTable();
			tableState.setDeletingCol(null);
		}

		isLoading = false;
	}

	async function handleDeleteRow() {
		if (isLoading || !isDeletingRow) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/${tableType}/rows/delete`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-project-id': page.params.project_id
				},
				body: JSON.stringify({
					table_id: page.params.table_id,
					row_ids: isDeletingRow
				})
			}
		);
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_DEL`), responseBody);
			toast.error('Failed to delete row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		} else {
			tableRowsState.rows = tableRowsState.rows?.filter((row) => !isDeletingRow?.includes(row.ID));
			await refetchTable();
			isDeletingRow = null;
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={() => !!tableState.deletingCol, () => tableState.setDeletingCol(null)}>
	<Dialog.Content
		data-testid="delete-column-dialog"
		class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]"
	>
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<div class="flex flex-col items-start gap-2 p-8">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want to drop column
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{tableState.deletingCol}`
				</span>? This process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					variant="destructive"
					onclick={handleDeleteColumn}
					type="button"
					loading={isLoading}
					class="grow px-6"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={() => !!isDeletingRow, () => (isDeletingRow = null)}>
	<Dialog.Content
		data-testid="delete-row-dialog"
		class=" w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]"
	>
		<Dialog.Close
			class="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full !bg-transparent p-0 ring-offset-background transition-colors hover:!bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-black"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</Dialog.Close>

		<div class="flex flex-col items-start gap-2 p-8">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="text-2xl font-bold">Are you sure?</h3>
			<p class="text-sm text-text/60">
				Do you really want to delete these row(s)? This process cannot be undone.
			</p>

			<div class="flex flex-col gap-1 p-2 text-sm">
				{#if isDeletingRow}
					{@const displayLimit = 5}
					{#each isDeletingRow as row, index}
						{#if index < displayLimit}
							<span>{row}</span>
						{/if}
					{/each}
					{#if isDeletingRow.length > displayLimit}
						<span>... and {isDeletingRow.length - displayLimit} more item(s)</span>
					{/if}
				{/if}
			</div>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					variant="destructive"
					onclick={handleDeleteRow}
					type="button"
					loading={isLoading}
					class="grow px-6"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
