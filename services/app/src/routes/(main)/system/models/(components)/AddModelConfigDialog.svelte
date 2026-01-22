<script lang="ts">
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import { invalidate } from '$app/navigation';
	import { MODEL_CAPABILITIES, MODEL_TYPES, modelLogos } from '$lib/constants';
	import { getModelIcon } from '$lib/utils';
	import type { ModelConfig } from '$lib/types';
	import type { LayoutData } from '../$types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';

	let { open = $bindable(), data }: { open?: boolean; data: LayoutData } = $props();

	let selectedSuggestedConfig = $state<ModelConfig | null>(null);

	let modelType = $state<string>();
	let baseTier = $state<string>();
	let modelIcon = $state<string>();
	let loading = $state(false);
	let currentStep = $state(0);
	const steps = ['Basic Information', 'Model Specifications', 'Cost Configuration'];
	let totalSteps = $derived(steps.length);

	function stringToArray(value: string): string[] {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	}

	let selectedCapabilities = $state<string[]>([]);

	function toggleCapability(capability: string) {
		if (selectedCapabilities.includes(capability)) {
			selectedCapabilities = selectedCapabilities.filter((c) => c !== capability);
		} else {
			selectedCapabilities = [...selectedCapabilities, capability];
		}
	}

	function nextStep() {
		// Validate current step
		if (currentStep === 0) {
			// Basic Information validation
			const nameInput = document.querySelector('input[name="name"]') as HTMLInputElement;
			const idInput = document.querySelector('input[name="id"]') as HTMLInputElement;

			if (!nameInput?.value) {
				toast.error('Model name is required', {
					id: 'model-name-required'
				});
				return;
			}

			if (!idInput?.value) {
				toast.error('Model ID is required', {
					id: 'model-id-required'
				});
				return;
			}

			if (!modelType) {
				toast.error('Model type is required', {
					id: 'model-type-required'
				});
				return;
			}

			if (selectedCapabilities.length === 0) {
				toast.error('At least one capability is required', {
					id: 'capability-required'
				});
				return;
			}
		}

		if (currentStep === 1) {
			// Model Specifications validation
			const contextLengthInput = document.querySelector(
				'input[name="context_length"]'
			) as HTMLInputElement;

			if (!contextLengthInput?.value) {
				toast.error('Context Length is required', {
					id: 'context-length-required'
				});
				return;
			}
		}

		if (currentStep < totalSteps) {
			currentStep++;
		}
	}

	function prevStep() {
		if (currentStep > 0) {
			currentStep--;
		}
	}

	$effect(() => {
		if (open) {
			untrack(() => {
				currentStep = 0;
				selectedSuggestedConfig = null;
				selectedCapabilities = [];
				modelType = undefined;
			});
		}
	});
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="flex h-[80vh] w-[clamp(0%,50rem,100%)] flex-col">
		<Dialog.Header class="mb-2">
			<Dialog.Title>Add Model Config</Dialog.Title>
		</Dialog.Header>

		<div class="flex flex-1 gap-4 overflow-hidden px-5">
			<section class="flex w-2/5 flex-col space-y-2 overflow-hidden">
				<h4 class="text-sm text-gray-500">SUGGESTED MODELS</h4>
				<div class="flex-1 overflow-y-auto pb-1 pr-2">
					{#if data.modelPresets.data}
						<div class="grid gap-4">
							{#each data.modelPresets.data.filter((p) => p.deployments[0].routing_id) as config}
								<div
									class="flex min-h-[80px] items-start justify-between rounded-xl border-[1.5px] border-gray-300 px-4 py-3 {selectedSuggestedConfig?.id ===
									config.id
										? 'bg-[#F9FFDB]'
										: 'bg-gray-50'}"
								>
									<div>
										<h5 class="text-sm text-gray-700">{config.name}</h5>
										<p class="text-xs text-gray-400">{config.id}</p>
									</div>
									<Checkbox
										bind:checked={
											() => config.id === selectedSuggestedConfig?.id,
											(v) => {
												currentStep = 0;
												if (v) {
													selectedSuggestedConfig = config;
													modelType = config.type;
													selectedCapabilities = config.capabilities;
													modelIcon = (config?.meta?.icon as string) || undefined;
												} else {
													selectedSuggestedConfig = null;
													modelType = undefined;
													selectedCapabilities = [];
													modelIcon = undefined;
												}
											}
										}
										class="border-gray-400 data-[state=checked]:bg-[#1B748A]"
									/>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</section>
			<form
				method="POST"
				id="addModelConfig"
				use:enhance={({ formData, cancel }) => {
					if (!modelType) {
						toast.error('Model type is required');
						cancel();
						return;
					}

					if (selectedCapabilities.length === 0) {
						toast.error('At least one capability is required');
						cancel();
						return;
					}

					loading = true;
					if (modelIcon) {
						formData.set('icon', modelIcon);
					}
					if (baseTier) {
						formData.set('base_tier_id', baseTier);
					}
					formData.set('type', modelType);
					formData.set('capabilities', JSON.stringify(selectedCapabilities));

					const languages = formData.get('languages');
					if (languages) {
						formData.set('languages', JSON.stringify(stringToArray(languages.toString())));
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
							open = false;
							toast.success('Model config added successfully', {
								id: 'add-model-config-success'
							});
							selectedCapabilities = [];
						}

						loading = false;
						await update({ invalidateAll: false });
						await invalidate('system:models');
					};
				}}
				action="?/add-model-config"
				class="flex w-3/5 flex-col space-y-6 overflow-y-auto p-1 pr-0"
			>
				<div>
					<div class="flex items-center justify-center">
						{#each steps as _, i}
							<div class="mb-2 flex items-center">
								<div
									class="flex h-5 w-5 items-center justify-center rounded-full text-xs transition-colors duration-300 ease-in-out {currentStep >=
									i
										? 'bg-gray-700 text-white'
										: 'bg-gray-200 text-gray-500'}"
								>
									{i + 1}
								</div>
								{#if i < steps.length - 1}
									<div
										class="h-[2px] w-[7vw] transition-colors duration-300 ease-in-out lg:w-[9vw] 2xl:w-[10vw] {currentStep >
										i
											? 'bg-gray-700'
											: 'bg-gray-200'}"
									></div>
								{/if}
							</div>
						{/each}
					</div>
					<div class="flex justify-between px-2 text-xs text-gray-500">
						{#each steps as step, i}
							<div
								class="text-center transition-opacity duration-300 ease-in-out {currentStep === i
									? 'font-medium opacity-100'
									: 'opacity-70'}"
							>
								{step}
							</div>
						{/each}
					</div>
				</div>

				<div class="flex-1 rounded-xl bg-gray-100 px-4 py-3">
					<div class="hidden space-y-6" class:!block={currentStep === 0}>
						<div class="space-y-1">
							<Label required>Model Name</Label>
							<Input
								value={selectedSuggestedConfig?.name}
								required
								name="name"
								placeholder="Model name"
								class="bg-white"
							/>
						</div>

						<div class="space-y-1">
							<Label required>Model ID</Label>
							<Input
								value={selectedSuggestedConfig?.id}
								required
								name="id"
								placeholder="Model ID"
								class="bg-white"
							/>
						</div>

						<div class="space-y-1">
							<Label>Model Icon</Label>
							<Select.Root name="model-icon" type="single" bind:value={modelIcon}>
								<Select.Trigger class="flex w-full items-center gap-2 bg-white">
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

						<div class="space-y-1">
							<Label required>Model Type</Label>
							<Select.Root required name="type" type="single" bind:value={modelType}>
								<Select.Trigger class="bg-white">
									{MODEL_TYPES[modelType ?? ''] || 'Select model type'}
								</Select.Trigger>
								<Select.Content>
									{#each Object.keys(MODEL_TYPES) as modelType}
										<Select.Item value={modelType}>
											{MODEL_TYPES[modelType]}
										</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						</div>

						<div class="col-span-2 space-y-1">
							<Label required>Capabilities</Label>
							<div class="flex flex-wrap gap-2">
								{#each Object.entries(MODEL_CAPABILITIES) as [capability, label]}
									<!-- A11y: visible, non-interactive elements with an onclick event must be accompanied by a keyboard event handler. -->
									<button
										type="button"
										class="cursor-pointer rounded-full border border-green-300 px-3 py-1 text-sm"
										class:bg-[#F5FFDB]={selectedCapabilities.includes(capability)}
										onclick={() => toggleCapability(capability)}
									>
										{label}
									</button>
								{/each}
							</div>
						</div>

						<div class="space-y-1">
							<Label>Priority</Label>
							<Input
								value={selectedSuggestedConfig?.priority}
								name="priority"
								placeholder="Priority"
								class="bg-white"
							/>
						</div>

						<div class="space-y-1">
							<Label>Owned By</Label>
							<Input
								value={selectedSuggestedConfig?.owned_by}
								name="owned_by"
								placeholder="Owned By"
								class="bg-white"
							/>
						</div>
					</div>

					<div class="hidden space-y-6" class:!block={currentStep === 1}>
						<div class="space-y-1">
							<Label required>Context Length</Label>
							<Input
								value={selectedSuggestedConfig?.context_length}
								required
								type="number"
								name="context_length"
								class="bg-white"
							/>
						</div>

						{#if modelType === 'embed'}
							<div class="space-y-1">
								<Label>Embedding size</Label>
								<Input
									value={selectedSuggestedConfig?.embedding_size}
									type="number"
									min="0"
									step="1"
									name="embedding_size"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Dimensions</Label>
								<Input
									value={selectedSuggestedConfig?.embedding_dimensions}
									type="number"
									min="0"
									step="1"
									name="embedding_dimensions"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Transform Query</Label>
								<Input
									value={selectedSuggestedConfig?.embedding_transform_query}
									name="embedding_transform_query"
									class="bg-white"
								/>
							</div>
						{/if}
						<div class="space-y-1">
							<Label>Languages (comma-separated)</Label>
							<Input
								value={selectedSuggestedConfig?.languages.join(', ')}
								name="languages"
								placeholder="en, es, fr"
								class="bg-white"
							/>
						</div>
					</div>

					<div class="hidden space-y-6" class:!block={currentStep === 2}>
						{#if modelType === 'llm'}
							<div class="space-y-1">
								<Label>Cost in USD per million input tokens</Label>
								<Input
									value={selectedSuggestedConfig?.llm_input_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="llm_input_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Cost in USD per million output tokens</Label>
								<Input
									value={selectedSuggestedConfig?.llm_output_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="llm_output_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
						{/if}
						{#if modelType === 'embed'}
							<div class="space-y-1">
								<Label>Cost in USD per million embedding tokens</Label>
								<Input
									value={selectedSuggestedConfig?.embedding_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="embedding_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
						{/if}
						{#if modelType === 'rerank'}
							<div class="space-y-1">
								<Label>Cost in USD for a thousand searches</Label>
								<Input
									value={selectedSuggestedConfig?.reranking_cost_per_ksearch}
									type="number"
									min="0"
									step=".000001"
									name="reranking_cost_per_ksearch"
									class="bg-white"
								/>
							</div>
						{/if}
						{#if modelType === 'image_gen'}
							<div class="space-y-1">
								<Label>Cost in USD per million input tokens</Label>
								<Input
									value={selectedSuggestedConfig?.llm_input_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="llm_input_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Cost in USD per million output tokens</Label>
								<Input
									value={selectedSuggestedConfig?.llm_output_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="llm_output_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Cost in USD per million image input tokens</Label>
								<Input
									value={selectedSuggestedConfig?.image_input_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="image_input_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
							<div class="space-y-1">
								<Label>Cost in USD per million image output tokens</Label>
								<Input
									value={selectedSuggestedConfig?.image_output_cost_per_mtoken}
									type="number"
									min="0"
									step=".000001"
									name="image_output_cost_per_mtoken"
									class="bg-white"
								/>
							</div>
						{/if}
					</div>
				</div>
			</form>
		</div>

		<Dialog.Actions class="border-t-[1px]">
			<div class="flex justify-end gap-2">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				{#if currentStep > 0}
					<Button tvTheme variant="outline" type="button" onclick={prevStep}>Back</Button>
				{/if}
				{#if currentStep < steps.length - 1}
					<Button tvTheme onclick={nextStep}>Next</Button>
				{:else}
					<Button tvTheme type="submit" form="addModelConfig" {loading} disabled={loading}>
						Create
					</Button>
				{/if}
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
