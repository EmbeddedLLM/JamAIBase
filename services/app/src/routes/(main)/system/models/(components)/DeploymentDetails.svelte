<script lang="ts">
	import { fade } from 'svelte/transition';
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import { invalidate } from '$app/navigation';
	import type { ModelDeployment } from '$lib/types';
	import type { LayoutData } from '../$types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Select from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import { PROVIDERS } from '$lib/constants';

	let {
		deployment
	}: {
		deployment: {
			data: ModelDeployment | null;
			error?: any;
			status?: number;
			refetch: () => void;
		};
	} = $props();

	let loading = $state(false);
	let isEditing = $state(false);
	let selectedProvider = $state<string>(deployment.data?.provider || '');

	$effect(() => {
		selectedProvider = deployment.data?.provider || '';
	});
</script>

<form
	method="POST"
	id="editModelDeployment"
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
				isEditing = false;
				toast.success('Model deployment updated successfully', {
					id: 'edit-deployment-success'
				});
			}

			loading = false;
			update({ invalidateAll: false });
			invalidate('system:models');
			invalidate('system:modelsslug');
			deployment.refetch();
		};
	}}
	action="/system/models?/edit-deployment"
	class="grow overflow-y-scroll py-1"
>
	<div class="grid grid-cols-1 {isEditing ? '[&>div]:px-3 [&>div]:py-0.5' : '[&>div]:p-3'}">
		<div class="flex items-center justify-start border-b-[1px]">
			<Label class="min-w-[20rem]">Model ID</Label>
			{#if isEditing}
				<Input
					class="w-[30rem]"
					required
					readonly
					name="model_id"
					placeholder="Model ID"
					value={deployment.data?.model_id}
				/>
			{:else}
				<div class="text-sm text-gray-800">{deployment.data?.model_id}</div>
			{/if}
		</div>

		<div class="flex items-center justify-start border-b-[1px]">
			<Label class="min-w-[20rem]">Deployment Name</Label>
			{#if isEditing}
				<Input
					required
					name="name"
					placeholder="Deployment name"
					value={deployment.data?.name}
					class="w-[30rem]"
				/>
			{:else}
				<div class="text-sm text-gray-800">{deployment.data?.name}</div>
			{/if}
		</div>

		<Input type="hidden" name="id" value={deployment.data?.id} class="w-[30rem]" />

		<!-- Cloud deployment fields -->
		<div class="flex items-center justify-start border-b-[1px]">
			<Label class="min-w-[20rem]">Provider</Label>
			{#if isEditing}
				{#await (page.data as LayoutData).providers}
					<Input class="w-[30rem]" placeholder="Loading providers..." disabled />
				{:then providers}
					<Select.Root type="single" bind:value={selectedProvider}>
						<Select.Trigger class="w-[30rem] min-w-0">
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
			{:else}
				<div class="text-sm text-gray-800">
					{PROVIDERS[deployment.data?.provider ?? ''] || deployment.data?.provider || '-'}
				</div>
			{/if}
		</div>

		<div class="flex items-center justify-start border-b-[1px]">
			<Label class="min-w-[20rem]">Routing ID</Label>
			{#if isEditing}
				<Input
					required
					name="routing_id"
					value={deployment.data?.routing_id}
					placeholder="provider/model_id"
					class="w-[30rem]"
				/>
			{:else}
				<div class="text-sm text-gray-800">{deployment.data?.routing_id || '-'}</div>
			{/if}
		</div>

		<div class="flex items-center justify-start border-b-[1px]">
			<Label class="min-w-[20rem]">API Base</Label>
			{#if isEditing}
				<Input
					name="api_base"
					value={deployment.data?.api_base}
					placeholder="Hosting url for the model"
					class="w-[30rem]"
				/>
			{:else}
				<div class="text-sm text-gray-800">{deployment.data?.api_base || '-'}</div>
			{/if}
		</div>

		<div class="flex items-center justify-start">
			<Label class="min-w-[20rem]">Weight</Label>
			{#if isEditing}
				<Input
					name="weight"
					placeholder="Routing weight. Must be >= 0. A deployment is selected according to its relative weight."
					value={deployment.data?.weight}
					defaultValue={1}
					class="w-[30rem]"
				/>
			{:else}
				<div class="text-sm text-gray-800">{deployment.data?.weight || 1}</div>
			{/if}
		</div>
	</div>
</form>

{#if !isEditing}
	<div transition:fade={{ duration: 150 }} class="fixed bottom-14 right-14">
		<button
			type="button"
			onclick={() => (isEditing = true)}
			class="rounded-full bg-[#1B748A] p-4 transition-colors hover:bg-[#145B6D]"
		>
			<EditIcon class="h-7 text-white" />
		</button>
	</div>
{:else}
	<div
		transition:fade={{ duration: 150 }}
		class="sticky bottom-0 flex w-full items-center justify-end space-x-3 bg-white px-4 py-3 shadow-[0_-2px_3px_0px_rgba(0,0,0,0.1)]"
	>
		<Button
			size="sm"
			onclick={() => (isEditing = false)}
			class="bg-gray-200 text-gray-600 hover:bg-gray-300 active:bg-gray-300"
		>
			Cancel
		</Button>
		<Button tvTheme size="sm" type="submit" form="editModelDeployment" {loading} disabled={loading}>
			Save Changes
		</Button>
	</div>
{/if}
