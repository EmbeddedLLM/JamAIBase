<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/stores';
	import { invalidate } from '$app/navigation';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import logger from '$lib/logger';

	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	export let tableType: 'action' | 'knowledge' | 'chat';
	export let isDeletingColumn: string | null;
	export let isDeletingRow: string[] | null;

	let isLoading = false;

	async function handleDeleteColumn() {
		if (isLoading || !isDeletingColumn) return;
		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/columns/drop`,
			{
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					table_id: $page.params.table_id,
					column_names: [isDeletingColumn]
				})
			}
		);
		if (!response.ok) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_COLUMN_DEL`), responseBody);
			toast.error('Failed to delete column', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
		} else {
			invalidate(`${tableType}-table:slug`);
			isDeletingColumn = null;
		}

		isLoading = false;
	}

	async function handleDeleteRow() {
		if (isLoading || !isDeletingRow) return;
		isLoading = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/delete`, {
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
			logger.error(toUpper(`${tableType}TBL_ROW_DEL`), responseBody);
			toast.error('Failed to delete row', {
				description: responseBody.message || JSON.stringify(responseBody)
			});
		} else {
			invalidate(`${tableType}-table:slug`);
			isDeletingRow = null;
		}

		isLoading = false;
	}
</script>

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
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleDeleteColumn}
					variant="destructive"
					type="button"
					loading={isLoading}
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
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					on:click={handleDeleteRow}
					variant="destructive"
					type="button"
					loading={isLoading}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
