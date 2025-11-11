<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import { getTableRowsState } from '$lib/components/tables/tablesState.svelte';

	const tableRowsState = getTableRowsState();

	interface Props {
		isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null;
		deleteCb: () => void;
	}

	let { isDeletingFile = $bindable(), deleteCb }: Props = $props();
</script>

<Dialog.Root bind:open={() => !!isDeletingFile, () => (isDeletingFile = null)}>
	<Dialog.Content
		data-testid="delete-file-dialog"
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
				Do you really want to delete file
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{isDeletingFile?.fileUri
						? isDeletingFile.fileUri.split('/').pop()
						: tableRowsState.rows
								?.find((row) => row.ID == isDeletingFile?.rowID)
								?.[isDeletingFile?.columnID ?? ''].value.split('/')
								.pop()}`
				</span>?
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
					onclick={deleteCb}
					type="button"
					loading={false}
					class="grow px-6"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
