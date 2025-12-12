<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/state';
	import logger from '$lib/logger';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	let {
		isDeletingConv = $bindable(),
		deleteCb
	}: { isDeletingConv: string | null; deleteCb?: () => void } = $props();

	let isLoading = $state(false);

	async function handleDeleteConv() {
		if (!isDeletingConv) return;

		isLoading = true;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/conversations?${new URLSearchParams([
				['conversation_id', isDeletingConv]
			])}`,
			{
				method: 'DELETE',
				headers: {
					'x-project-id': page.params.project_id ?? page.url.searchParams.get('project_id') ?? ''
				}
			}
		);
		const responseBody = await response.json();

		if (response.ok) {
			deleteCb?.();
			isDeletingConv = null;
		} else {
			logger.error('CHAT_CONV_DELETE', responseBody);
			toast.error('Failed to delete conversation', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		isLoading = false;
	}
</script>

<Dialog.Root bind:open={() => !!isDeletingConv, () => (isDeletingConv = null)}>
	<Dialog.Content
		data-testid="delete-conv-dialog"
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
				Do you really want to delete conversation
				<span class="font-medium text-black [word-break:break-word] data-dark:text-white">
					`{isDeletingConv}`
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
					onclick={handleDeleteConv}
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
