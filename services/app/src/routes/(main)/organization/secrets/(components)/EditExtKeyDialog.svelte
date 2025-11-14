<script lang="ts">
	import { enhance } from '$app/forms';
	import { PROVIDERS } from '$lib/constants';
	import type { OrganizationReadRes } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	let {
		organizationData,
		isEditingExtKey = $bindable()
	}: {
		organizationData: OrganizationReadRes | undefined;
		isEditingExtKey: { open: boolean; value: string | null };
	} = $props();

	let loadingEditExtKey = $state(false);
	let customProvider = $state(false);
	let selectedProvider = $state(isEditingExtKey.value || '');

	$effect(() => {
		if (isEditingExtKey.value) {
			selectedProvider = isEditingExtKey.value;
			customProvider = !Object.keys(PROVIDERS).includes(isEditingExtKey.value);
		} else {
			selectedProvider = '';
			customProvider = false;
		}
	});
</script>

<Dialog.Root
	bind:open={() => isEditingExtKey.open, (v) => (isEditingExtKey = { ...isEditingExtKey, open: v })}
>
	<Dialog.Content class="h-fit max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>
			<Dialog.Title>{isEditingExtKey.value ? 'Edit' : 'Add'} API Key</Dialog.Title>
		</Dialog.Header>

		<form
			method="POST"
			id="updateExternalKeys"
			use:enhance={({ formData, cancel }) => {
				loadingEditExtKey = true;

				if (!formData.get('provider') || !organizationData) {
					cancel();
				} else {
					formData.set(
						formData.get('provider')?.toString()!,
						formData.get('external_key')?.toString() ?? ''
					);

					Object.keys(organizationData.external_keys).forEach((key) => {
						if (key !== formData.get('provider')?.toString()) {
							formData.append(key, organizationData.external_keys[key]);
						}
					});

					formData.delete('provider');
					formData.delete('external_key');
				}

				return async ({ update, result }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error('Error updating external keys', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						isEditingExtKey = { ...isEditingExtKey, open: false };
					}

					loadingEditExtKey = false;
					update({ reset: false });
				};
			}}
			action="?/update-external-keys"
			class="flex grow flex-col gap-3 overflow-auto py-3"
		>
			<div class="space-y-1 px-4 sm:px-6">
				<Label required>Provider</Label>
				{#if customProvider}
					<div class="flex gap-2">
						<Input
							required
							type="text"
							name="provider"
							placeholder="Required"
							bind:value={selectedProvider}
							class="flex-1"
						/>
						<Button
							type="button"
							variant="outline"
							onclick={() => {
								customProvider = false;
								selectedProvider = '';
							}}
							class="rounded-lg"
						>
							Select from List
						</Button>
					</div>
				{:else}
					<div class="flex gap-2">
						<Select.Root
							required
							name="provider"
							type="single"
							bind:value={selectedProvider}
							onValueChange={(value) => {
								selectedProvider = value;
							}}
						>
							<Select.Trigger class="w-full min-w-0">
								{PROVIDERS[selectedProvider] || 'Select a Provider'}
							</Select.Trigger>
							<Select.Content>
								<Select.Group>
									{#each Object.entries(PROVIDERS) as [key, value]}
										<Select.Item value={key}>{value}</Select.Item>
									{/each}
								</Select.Group>
							</Select.Content>
						</Select.Root>
						<Button
							type="button"
							variant="outline"
							onclick={() => {
								customProvider = true;
							}}
							class="rounded-lg"
						>
							Custom
						</Button>
					</div>
				{/if}
			</div>

			<div class="space-y-1 px-4 sm:px-6">
				<Label>API Key</Label>
				<Input
					name="external_key"
					type="text"
					value={organizationData?.external_keys[isEditingExtKey.value ?? '']}
				/>
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex justify-end gap-2">
				<Button
					type="button"
					onclick={() => (isEditingExtKey = { ...isEditingExtKey, open: false })}
					variant="link"
				>
					Cancel
				</Button>
				<Button
					form="updateExternalKeys"
					type="submit"
					loading={loadingEditExtKey}
					disabled={loadingEditExtKey}
				>
					Save changes
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
