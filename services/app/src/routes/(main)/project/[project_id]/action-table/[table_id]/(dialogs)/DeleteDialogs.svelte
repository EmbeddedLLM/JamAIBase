<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { page } from '$app/stores';
	import { goto, invalidate } from '$app/navigation';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { pastActionTables } from '../../actionTablesStore';
	import logger from '$lib/logger';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	export let isDeletingTable: string | null;
	export let isDeletingColumn: string | null;
	export let isDeletingRow: string[] | null;

	let isLoading = false;

	async function handleDeleteTable() {
		if (isLoading || !isDeletingTable) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/${isDeletingTable}`,
			{
				method: 'DELETE'
			}
		);
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_TBL_DEL', responseBody);
			alert('Failed to delete table: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			$pastActionTables = $pastActionTables.filter((t) => t.id !== isDeletingTable);
			if ($page.params.table_id === isDeletingTable) {
				goto(`/project/${$page.params.project_id}/action-table/${$pastActionTables[0]?.id || ''}`);
			}
			isDeletingTable = null;
		}

		isLoading = false;
	}

	async function handleDeleteColumn() {
		if (isLoading || !isDeletingColumn) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/columns/drop`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				column_names: [isDeletingColumn]
			})
		});
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_COLUMN_DEL', responseBody);
			alert('Failed to delete column: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			invalidate('action-table:slug');
			isDeletingColumn = null;
		}

		isLoading = false;
	}

	async function handleDeleteRow() {
		if (isLoading || !isDeletingRow) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/action/rows/delete`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				where: `\`ID\` IN (${isDeletingRow.map((i) => `'${i}'`).join(',')})`
			})
		});
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('ACTIONTBL_ROW_DEL', responseBody);
			alert('Failed to delete row: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			invalidate('action-table:slug');
			isDeletingRow = null;
		}

		isLoading = false;
	}
</script>

<Dialog.Root
	open={!!isDeletingTable}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingTable = null;
		}
	}}
>
	<Dialog.Content class="w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to delete table
				<span class="font-medium text-black data-dark:text-white">`{isDeletingTable}`</span>? This
				process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isDeletingTable = null)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					variant="destructive"
					on:click={handleDeleteTable}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	open={!!isDeletingColumn}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingColumn = null;
		}
	}}
>
	<Dialog.Content class="w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to drop column
				<span class="font-medium text-black data-dark:text-white">`{isDeletingColumn}`</span>? This
				process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isDeletingColumn = null)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					variant="destructive"
					on:click={handleDeleteColumn}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root
	open={!!isDeletingRow}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingRow = null;
		}
	}}
>
	<Dialog.Content class="w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to delete these row(s)? This process cannot be undone.
			</p>

			<div class="flex flex-col gap-1 p-2 text-sm">
				{#if isDeletingRow}
					{@const displayLimit = 10}
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
			<div class="flex gap-2">
				<Button variant="link" on:click={() => (isDeletingRow = null)} class="grow px-6">
					Cancel
				</Button>
				<Button
					loading={isLoading}
					variant="destructive"
					on:click={handleDeleteRow}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
