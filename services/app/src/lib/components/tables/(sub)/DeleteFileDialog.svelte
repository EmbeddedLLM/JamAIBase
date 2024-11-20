<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import { genTableRows } from '../tablesStore';

	export let isDeletingFile: { rowID: string; columnID: string; fileUri?: string } | null;
	export let deleteCb: () => void;
</script>

<Dialog.Root
	open={!!isDeletingFile}
	onOpenChange={(e) => {
		if (!e) {
			isDeletingFile = null;
		}
	}}
>
	<Dialog.Content
		data-testid="delete-file-dialog"
		class="w-[clamp(0px,26rem,100%)] bg-white data-dark:bg-[#42464e]"
	>
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to delete file
				<span class="font-medium text-black data-dark:text-white [word-break:break-word]">
					`{isDeletingFile?.fileUri
						? isDeletingFile.fileUri.split('/').pop()
						: $genTableRows
								?.find((row) => row.ID == isDeletingFile?.rowID)
								?.[isDeletingFile?.columnID ?? ''].value.split('/')
								.pop()}`
				</span>?
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					variant="destructive"
					on:click={deleteCb}
					type="button"
					loading={false}
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
