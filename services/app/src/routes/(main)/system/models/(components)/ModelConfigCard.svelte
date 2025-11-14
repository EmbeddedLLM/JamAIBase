<script lang="ts">
	import { goto } from '$app/navigation';
	import { Copy, Ellipsis, Trash2 } from '@lucide/svelte';
	import { getModelIcon } from '$lib/utils';
	import type { ModelConfig } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { Button } from '$lib/components/ui/button';
	import EditIcon from '$lib/icons/EditIcon.svelte';

	let {
		modelConfig,
		editOpen = $bindable(),
		deleteOpen = $bindable(),
		deployOpen = $bindable(),
		currentPage
	}: {
		modelConfig: ModelConfig;
		editOpen: { open: boolean; value: ModelConfig | null };
		deleteOpen: { open: boolean; value: ModelConfig | null };
		deployOpen: { open: boolean; value: ModelConfig | null };
		currentPage: number;
	} = $props();

	let menuOpen = $state(false);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	onclick={() => {
		goto(`/system/models/${encodeURIComponent(modelConfig.id)}`, { state: { page: currentPage } });
	}}
	oncontextmenu={(e) => {
		e.preventDefault();
		menuOpen = !menuOpen;
	}}
	class="flex h-full cursor-pointer flex-col justify-start space-y-2 overflow-auto rounded-xl border border-[#E4E7EC] bg-white p-4 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-float"
	class:!bg-[#FFF8EA]={!modelConfig.deployments.length}
>
	<div>
		<img class="h-7 pb-2" {...getModelIcon(modelConfig.meta.icon)} />
	</div>
	<div class="space-y-2">
		<h3 class="text-lg font-medium">
			{modelConfig.name}
		</h3>
		<p class="flex items-center gap-1 pb-1 text-xs text-gray-400">
			{modelConfig.id}
			<Button
				variant="ghost"
				onclick={(e) => {
					e.stopPropagation();
					navigator.clipboard.writeText(modelConfig.id);
					toast.success('Model config ID copied to clipboard', { id: 'model-id-copied' });
				}}
				class="h-[unset] p-1"
			>
				<Copy class="h-3 w-3" />
			</Button>
		</p>
		<div class="flex gap-x-1">
			<div class="w-fit rounded-md bg-[#F5EDFF] px-2.5 py-0.5 text-xs uppercase text-[#916FD0]">
				{modelConfig.type}
			</div>
			{#if modelConfig.deployments.length}
				<div class="w-fit rounded-md bg-[#E9FFB5] px-2.5 py-0.5 text-xs text-[#29B054]">
					{modelConfig.deployments.length}
					{modelConfig.deployments.length === 1 ? 'deployment' : 'deployments'}
				</div>
			{:else}
				<div
					class="w-fit rounded-md bg-yellow-300/60 px-2.5 py-0.5 text-xs capitalize text-orange-600"
				>
					No Deployment
				</div>
			{/if}
		</div>
	</div>

	<div class=" flex flex-1 items-end justify-between">
		<Button
			tvTheme
			onclick={(e) => {
				e.stopPropagation();
				deployOpen = { open: true, value: modelConfig };
			}}
			class="model-config-deploy-btn h-[unset] rounded-xl px-3 py-2"
		>
			Deploy
		</Button>
		<DropdownMenu.Root bind:open={menuOpen}>
			<DropdownMenu.Trigger
				class="rounded-xl border p-1.5 px-2.5 transition-colors hover:bg-gray-100 focus:outline-none"
			>
				<Ellipsis class="h-5 w-5 text-gray-500 hover:text-gray-700" />
			</DropdownMenu.Trigger>
			<DropdownMenu.Content>
				<DropdownMenu.Item
					onclick={() => goto(`/system/models/${encodeURIComponent(modelConfig.id)}?edit=true`)}
					class="text-[#344054] data-[highlighted]:text-[#344054]"
				>
					<EditIcon class="mr-2 h-3.5" />
					<span>Edit</span>
				</DropdownMenu.Item>
				<DropdownMenu.Item
					onclick={() => (deleteOpen = { open: true, value: modelConfig })}
					class="text-destructive data-[highlighted]:text-destructive"
				>
					<Trash2 class="mr-2 h-3.5" />
					<span>Delete</span>
				</DropdownMenu.Item>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
	</div>
</div>
