<script lang="ts">
	import { fade, slide } from 'svelte/transition';
	import { enhance } from '$app/forms';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { ModelConfig } from '$lib/types';
	import { MODEL_CAPABILITIES, MODEL_TYPES, modelLogos } from '$lib/constants';
	import { getModelIcon } from '$lib/utils';

	import { DeleteModelConfigDialog } from '../../(components)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Select from '$lib/components/ui/select/index.js';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Trash2 } from '@lucide/svelte';

	let { model }: { model: ModelConfig } = $props();

	let isEditing = $derived(page.url.searchParams.get('edit') === 'true');
	let modelType = $state<ModelConfig['type'] | undefined>(model.type);
	let modelIcon = $state<string | undefined>(model.meta?.icon as string);
	let selectedCapabilities = $state<string[]>(model.capabilities || []);
	let loading = $state(false);

	let deleteOpen = $state<{ open: boolean; value: ModelConfig | null }>({
		open: false,
		value: null
	});

	function stringToArray(value: string): string[] {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	}

	function toggleCapability(capability: string) {
		if (selectedCapabilities.includes(capability)) {
			selectedCapabilities = selectedCapabilities.filter((c) => c !== capability);
		} else {
			selectedCapabilities = [...selectedCapabilities, capability];
		}
	}
</script>

<section class="relative">
	<form
		id="editModelConfigDetails"
		method="POST"
		use:enhance={({ formData, cancel }) => {
			if (!modelType) {
				toast.error('Model type is required', {
					id: 'model-type-required'
				});
				cancel();
				return;
			}

			if (selectedCapabilities.length === 0) {
				toast.error('At least one capability is required', {
					id: 'capability-required'
				});
				cancel();
				return;
			}

			loading = true;
			if (modelIcon) {
				formData.set('icon', modelIcon);
			}

			formData.set('type', modelType);
			formData.set('capabilities', JSON.stringify(selectedCapabilities));

			const languages = formData.get('languages');
			if (languages) {
				formData.set('languages', JSON.stringify(stringToArray(languages.toString())));
			}

			const allowed_orgs = formData.get('allowed_orgs');
			if (allowed_orgs) {
				formData.set('allowed_orgs', JSON.stringify(stringToArray(allowed_orgs.toString())));
			}

			const blocked_orgs = formData.get('blocked_orgs');
			if (blocked_orgs) {
				formData.set('blocked_orgs', JSON.stringify(stringToArray(blocked_orgs.toString())));
			}

			return async ({ update, result }) => {
				//@ts-ignore
				const data = result.data;
				if (result.type === 'failure') {
					toast.error(data.error, {
						id: data?.err_message?.message || JSON.stringify(data),
						description: CustomToastDesc as any,
						componentProps: {
							description: data?.err_message?.message || JSON.stringify(data),
							requestID: data?.err_message?.request_id ?? ''
						}
					});
				} else if (result.type === 'success') {
					toast.success('Model config updated successfully', {
						id: 'edit-model-config-success'
					});
					isEditing = false;

					page.url.searchParams.delete('edit');
					goto(
						`/system/models/${encodeURIComponent(formData.get('id')?.toString()!)}?${page.url.searchParams}`,
						{
							invalidate: ['system:models', 'system:modelsslug'],
							replaceState: true
						}
					);
				}

				update({ invalidateAll: false });
				loading = false;
			};
		}}
		action="?/edit-model-config"
		class="px-5 py-5"
		class:space-y-5={!isEditing}
	>
		<div class="grid grid-cols-[minmax(12rem,_2fr),_minmax(0,_5fr)]">
			<div>
				<p class="mt-4">Basic Information</p>
			</div>
			{#if isEditing}
				<div
					class="overflow-auto [&>div>*]:p-2 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<input type="hidden" name="model_id" value={model.id} />

					<div class="flex items-center border-b text-sm">
						<Label required class="text-gray-500">Model Name</Label>
						<div>
							<Input required name="name" placeholder="Model name" value={model.name} />
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label required class="text-gray-500">Model ID</Label>
						<div>
							<Input required name="id" value={model.id} />
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Model Icon</Label>
						<div>
							<Select.Root name="model-icon" type="single" bind:value={modelIcon}>
								<Select.Trigger class="flex w-full items-center gap-2">
									{#if modelIcon}
										<div class="flex items-center gap-2">
											<img class="h-5 w-5" {...getModelIcon(modelIcon)} />
											<span class="font-medium capitalize">{modelIcon}</span>
										</div>
									{:else}
										<span class="text-gray-500">Select model icon</span>
									{/if}
								</Select.Trigger>
								<Select.Content class="max-h-[300px] overflow-y-auto">
									{#each Object.keys(modelLogos) as icon}
										<Select.Item
											value={icon}
											class="flex items-center gap-3 px-3 py-2 pl-8 hover:bg-gray-100"
										>
											<img class="h-5 w-5" {...getModelIcon(icon)} />
											<span class="capitalize">{icon}</span>
										</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label required class="text-gray-500">Model Type</Label>
						<div>
							<Select.Root required name="type" type="single" bind:value={modelType}>
								<Select.Trigger>
									{MODEL_TYPES[modelType ?? ''] || 'Select model type'}
								</Select.Trigger>
								<Select.Content>
									{#each Object.keys(MODEL_TYPES) as type}
										<Select.Item value={type}>{MODEL_TYPES[type]}</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label required class="text-gray-500">Capabilities</Label>
						<div class="flex flex-wrap gap-2">
							{#each Object.entries(MODEL_CAPABILITIES) as [capability, label]}
								<button
									type="button"
									class="cursor-pointer rounded-full border border-green-400 px-3 py-1 text-sm"
									class:bg-[#F4FFD9]={selectedCapabilities.includes(capability)}
									onclick={() => toggleCapability(capability)}
								>
									{label}
								</button>
							{/each}
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Priority</Label>
						<div>
							<Input name="priority" value={model.priority} />
						</div>
					</div>

					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Owned By</Label>
						<div>
							<Input name="owned_by" value={model.owned_by} />
						</div>
					</div>
				</div>
			{:else}
				<div
					class="overflow-auto rounded-xl bg-gray-100 [&>div>*]:p-4 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Model Name</p>
						<p class="text-gray-700">{model.name}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Model ID</p>
						<p class="text-gray-700">{model.id}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Model Type</p>
						<div class="!py-3.5">
							<p class="w-max rounded-xl bg-[#E9D9FF] px-2 py-1 text-xs uppercase">{model.type}</p>
						</div>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Capabilities</p>
						<p class="text-gray-700">
							{model.capabilities.map((cap) => MODEL_CAPABILITIES[cap]).join(', ')}
						</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Priority</p>
						<p class="text-gray-700">{model.priority}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Owned By</p>
						<p class="text-gray-700">{model.owned_by}</p>
					</div>
				</div>
			{/if}
		</div>

		<div class="grid grid-cols-[minmax(12rem,_2fr),_minmax(0,_5fr)]">
			<div>
				<p class="mt-4">Model Specification</p>
			</div>
			{#if isEditing}
				<div
					class="overflow-auto [&>div>*]:p-2 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<div class="flex items-center border-b text-sm">
						<Label required class="text-gray-500">Context Length</Label>
						<div>
							<Input required type="number" name="context_length" value={model.context_length} />
						</div>
					</div>
					{#if modelType === 'embed'}
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Embedding size</Label>
							<div>
								<Input
									type="number"
									min="0"
									step="1"
									name="embedding_size"
									value={model.embedding_size}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Dimensions</Label>
							<div>
								<Input
									type="number"
									min="0"
									step="1"
									name="embedding_dimensions"
									value={model.embedding_dimensions}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Transform Query</Label>
							<div>
								<Input name="embedding_transform_query" value={model.embedding_transform_query} />
							</div>
						</div>
					{/if}
					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Languages (comma-separated)</Label>
						<div>
							<Input
								name="languages"
								placeholder="en, es, fr"
								value={model.languages?.join(', ')}
							/>
						</div>
					</div>
				</div>
			{:else}
				<div
					class="overflow-auto rounded-xl bg-gray-100 [&>div>*]:p-4 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Context Length</p>
						<p class="text-gray-700">{model.context_length}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Languages</p>
						<p class="text-gray-700">{model.languages.join(', ')}</p>
					</div>
				</div>
			{/if}
		</div>

		<div class="grid grid-cols-[minmax(12rem,_2fr),_minmax(0,_5fr)]">
			<div>
				<p class="mt-4">Cost Configuration</p>
			</div>
			{#if isEditing}
				<div
					class="overflow-auto [&>div>*]:p-2 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					{#if modelType === 'llm'}
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million input tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="llm_input_cost_per_mtoken"
									value={model.llm_input_cost_per_mtoken}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million output tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="llm_output_cost_per_mtoken"
									value={model.llm_output_cost_per_mtoken}
								/>
							</div>
						</div>
					{/if}
					{#if modelType === 'embed'}
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million embedding tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="embedding_cost_per_mtoken"
									value={model.embedding_cost_per_mtoken}
								/>
							</div>
						</div>
					{/if}
					{#if modelType === 'rerank'}
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD for a thousand searches</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="reranking_cost_per_ksearch"
									value={model.reranking_cost_per_ksearch}
								/>
							</div>
						</div>
					{/if}
					{#if modelType === 'image_gen'}
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million input tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="llm_input_cost_per_mtoken"
									value={model.llm_input_cost_per_mtoken}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million output tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="llm_output_cost_per_mtoken"
									value={model.llm_output_cost_per_mtoken}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million image input tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="image_input_cost_per_mtoken"
									value={model.image_input_cost_per_mtoken}
								/>
							</div>
						</div>
						<div class="flex items-center border-b text-sm">
							<Label class="text-gray-500">Cost in USD per million image output tokens</Label>
							<div>
								<Input
									type="number"
									min="0"
									step=".000001"
									name="image_output_cost_per_mtoken"
									value={model.image_output_cost_per_mtoken}
								/>
							</div>
						</div>
					{/if}
				</div>
			{:else}
				<div
					class="overflow-auto rounded-xl bg-gray-100 [&>div>*]:p-4 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					{#if modelType === 'llm'}
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million input tokens</p>
							<p class="text-gray-700">{model.llm_input_cost_per_mtoken}</p>
						</div>
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million output tokens</p>
							<p class="text-gray-700">{model.llm_output_cost_per_mtoken}</p>
						</div>
					{/if}
					{#if modelType === 'embed'}
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million embedding tokens</p>
							<p class="text-gray-700">{model.embedding_cost_per_mtoken}</p>
						</div>
					{/if}
					{#if modelType === 'rerank'}
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD for a thousand searches</p>
							<p class="text-gray-700">{model.reranking_cost_per_ksearch}</p>
						</div>
					{/if}
					{#if modelType === 'image_gen'}
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million input tokens</p>
							<p class="text-gray-700">{model.llm_input_cost_per_mtoken}</p>
						</div>
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million output tokens</p>
							<p class="text-gray-700">{model.llm_output_cost_per_mtoken}</p>
						</div>
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million image input tokens</p>
							<p class="text-gray-700">{model.image_input_cost_per_mtoken}</p>
						</div>
						<div class="border-b text-sm last:border-b-0">
							<p class="text-gray-500">Cost in USD per million image output tokens</p>
							<p class="text-gray-700">{model.image_output_cost_per_mtoken}</p>
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="grid grid-cols-[minmax(12rem,_2fr),_minmax(0,_5fr)]">
			<div>
				<p class="mt-4">Access Control</p>
			</div>
			{#if isEditing}
				<div
					class="overflow-auto [&>div>*]:p-2 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Allowed Orgs (comma-separated)</Label>
						<div>
							<Input name="allowed_orgs" placeholder="" value={model.allowed_orgs.join(', ')} />
						</div>
					</div>
					<div class="flex items-center border-b text-sm">
						<Label class="text-gray-500">Blocked Orgs (comma-separated)</Label>
						<div>
							<Input name="blocked_orgs" placeholder="" value={model.blocked_orgs.join(', ')} />
						</div>
					</div>
				</div>
			{:else}
				<div
					class="overflow-auto rounded-xl bg-gray-100 [&>div>*]:p-4 [&>div]:grid [&>div]:grid-cols-[minmax(18rem,_2fr)_minmax(20rem,_5fr)]"
				>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Allowed Orgs</p>
						<p class="text-gray-700">{model.allowed_orgs.join(', ')}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Blocked Orgs</p>
						<p class="text-gray-700">{model.blocked_orgs.join(', ')}</p>
					</div>
					<div class="border-b text-sm last:border-b-0">
						<p class="text-gray-500">Is Private</p>
						<div class="flex items-center">
							<Checkbox
								checked={model.is_private}
								class="pointer-events-none border-gray-400 data-[state=checked]:bg-[#1B748A]"
							/>
						</div>
					</div>
				</div>
			{/if}
		</div>
	</form>
	{#if !isEditing}
		<div transition:fade={{ duration: 150 }} class="fixed bottom-20 right-20">
			<button
				onclick={() => {
					page.url.searchParams.append('edit', 'true');
					goto(`?${page.url.searchParams}`, { invalidate: [], replaceState: true });
				}}
				class="rounded-full bg-[#1B748A] p-4 transition-colors hover:bg-[#145B6D]"
			>
				<EditIcon class="h-6 text-white" />
			</button>

			<button
				onclick={() => {
					deleteOpen = { open: true, value: model };
				}}
				class="rounded-full bg-destructive p-4 transition-colors hover:bg-destructive/90"
			>
				<Trash2 class="h-6 text-white" />
			</button>
		</div>
	{:else}
		<div
			transition:slide={{ duration: 150 }}
			class="sticky bottom-0 flex w-full items-center justify-end gap-2 bg-white px-4 py-3 shadow-[0_-2px_3px_0px_rgba(0,0,0,0.1)]"
		>
			<Button
				size="sm"
				onclick={() => {
					page.url.searchParams.delete('edit');
					goto(`?${page.url.searchParams}`, { invalidate: [], replaceState: true });
				}}
				class="bg-gray-200 text-gray-500 hover:bg-gray-300 active:bg-gray-300"
			>
				Cancel
			</Button>
			<Button
				tvTheme
				size="sm"
				type="submit"
				form="editModelConfigDetails"
				{loading}
				disabled={loading}
			>
				Save Changes
			</Button>
		</div>
	{/if}
</section>

<DeleteModelConfigDialog bind:open={deleteOpen} />
