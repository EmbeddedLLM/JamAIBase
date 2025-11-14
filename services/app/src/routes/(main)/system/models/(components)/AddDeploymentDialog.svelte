<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { invalidate } from '$app/navigation';
	import { PROVIDERS } from '$lib/constants';
	import type { ModelConfig } from '$lib/types';
	import type { LayoutData } from '../$types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';

	let {
		open = $bindable()
	}: {
		open: { open: boolean; value: ModelConfig | null };
	} = $props();

	let modelPresets = (page.data as LayoutData).modelPresets;
	let modelPreset = $derived(modelPresets.data?.find((p) => p.id === open.value?.id));
	let deploymentPreset = $derived(
		modelPreset?.deployments?.length ? modelPreset.deployments[0] : null
	);

	let loading = $state(false);

	let selectedProvider = $state<string>('');
</script>

<Dialog.Root bind:open={() => open.open, (v) => (open = { ...open, open: v })}>
	<Dialog.Content class="w-[clamp(0%,37rem,80%)]">
		<Dialog.Header>Deploy model</Dialog.Header>
		<form
			method="POST"
			action="/system/models?/add-deployment"
			id="addDeployment"
			use:enhance={({ formData }) => {
				loading = true;
				formData.set('provider', selectedProvider);

				return async ({ update, result }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error(data.error, {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						open = { ...open, open: false };
						toast.success('Model deployment added successfully', {
							id: 'add-deployment-success'
						});

						update({ invalidateAll: false });
						invalidate('system:models');
						invalidate('system:modelsslug');
					}

					loading = false;
				};
			}}
			class="flex grow flex-col gap-3 overflow-y-scroll px-4 py-3 sm:px-6"
		>
			<div class="space-y-1">
				<Label required>Model ID</Label>
				<Input value={open.value?.id} required readonly name="model_id" placeholder="Model ID" />
			</div>

			<div class="space-y-1">
				<Label required>Deployment Name</Label>
				<Input required name="name" value={deploymentPreset?.name} placeholder="Deployment name" />
			</div>

			<div class="space-y-1">
				<Label required>Provider</Label>
				{#await (page.data as LayoutData).providers}
					<Input name="provider" placeholder="Loading providers..." disabled />
				{:then providers}
					<Select.Root name="provider" type="single" bind:value={selectedProvider}>
						<Select.Trigger>
							{PROVIDERS[selectedProvider] || selectedProvider || 'Select a provider'}
						</Select.Trigger>
						<Select.Content>
							<!-- TODO: Handle error here -->
							{#if providers.data}
								{#each providers.data.filter((p) => p !== '') as provider}
									<Select.Item value={provider} label={PROVIDERS[provider]}>
										{PROVIDERS[provider] || provider}
									</Select.Item>
								{/each}
							{/if}
						</Select.Content>
					</Select.Root>
				{/await}
			</div>

			<div class="space-y-1">
				<Label required>Routing ID</Label>
				<Input
					required
					name="routing_id"
					value={deploymentPreset?.routing_id}
					placeholder="provider/model_id"
				/>
			</div>

			<div class="space-y-1">
				<Label>API Base</Label>
				<Input
					name="api_base"
					value={deploymentPreset?.api_base}
					placeholder="Hosting url for the model"
				/>
			</div>

			<div class="space-y-1">
				<Label>Weight</Label>
				<Input
					name="weight"
					placeholder="Routing weight. Must be >= 0. A deployment is selected according to its relative weight."
					defaultValue={1}
				/>
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex justify-end gap-2">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} class="text-gray-600" variant="link" type="button">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					tvTheme
					type="submit"
					form="addDeployment"
					{loading}
					disabled={loading}
					class="rounded-full"
				>
					Deploy
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
