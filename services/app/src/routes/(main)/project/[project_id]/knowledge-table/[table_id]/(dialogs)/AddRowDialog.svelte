<script lang="ts">
	import { page } from '$app/stores';
	import type { ActionTable } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';

	export let isAddingRow: boolean;
	export let addRowFunction: (data: any) => Promise<void>;
	export let isLoadingAddRow: boolean;

	$: tableData = $page.data.table?.tableData as ActionTable; // For types

	let form: HTMLFormElement;

	async function handleAddRow(e: SubmitEvent) {
		if (isLoadingAddRow) return;
		const form = e.target as HTMLFormElement;
		const formData = new FormData(form);
		const obj = Object.fromEntries(
			Array.from(formData.keys()).map((key) => [
				key,
				formData.getAll(key).length > 1 ? formData.getAll(key) : formData.get(key)
			])
		);

		// Check if all required fields are filled
		if (
			Object.keys(obj).some(
				(key) => !tableData.cols.find((col) => col.id == key)?.gen_config && !obj[key]
			)
		) {
			return alert('Please fill in all required fields');
		}

		await addRowFunction(
			Object.fromEntries(
				Object.entries(obj).filter(([key, value]) => value !== '' && value !== null)
			)
		);
	}
</script>

<Dialog.Root bind:open={isAddingRow}>
	<Dialog.Content class="max-h-[90vh] min-w-[35rem]">
		<Dialog.Header>New row</Dialog.Header>

		<form
			bind:this={form}
			on:submit|preventDefault={handleAddRow}
			class="grow w-full overflow-auto"
		>
			<div class="grow py-3 h-full w-full overflow-auto">
				{#if !tableData.cols.filter((col) => col.id !== 'ID' && col.id !== 'Updated at').length}
					<div class="flex items-center justify-center w-full h-32">
						<p class="text-[#999] data-dark:text-[#C9C9C9]">No columns</p>
					</div>
				{:else}
					{#each tableData.cols.filter((col) => col.id !== 'ID' && col.id !== 'Updated at') as column}
						<div class="flex flex-col gap-2 px-6 pl-8 py-2 w-full text-center">
							<span class="font-medium text-left text-sm text-[#999] data-dark:text-[#C9C9C9]">
								{column.id} ({column.dtype}){!column.gen_config ? '*' : ''}
							</span>

							<input
								type="text"
								id={column.id}
								name={column.id}
								placeholder={column.gen_config ? 'Optional, generated' : 'Required'}
								class="px-3 py-2 w-full text-sm bg-transparent data-dark:bg-[#42464e] rounded-md border border-[#DDD] data-dark:border-[#42464E] placeholder:italic focus-visible:outline-none focus-visible:border-[#4169e1] data-dark:focus-visible:border-[#5b7ee5] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
							/>
						</div>
					{/each}
				{/if}
			</div>

			<!-- hidden submit -->
			<Button
				type="submit"
				loading={isLoadingAddRow}
				class="hidden relative grow px-6 rounded-full"
			>
				Add
			</Button>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2">
				<Button
					variant="link"
					type="button"
					on:click={() => (isAddingRow = false)}
					class="grow px-6"
				>
					Cancel
				</Button>
				<Button
					on:click={() => form.requestSubmit()}
					loading={isLoadingAddRow}
					class="relative grow px-6 rounded-full"
				>
					Add
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
