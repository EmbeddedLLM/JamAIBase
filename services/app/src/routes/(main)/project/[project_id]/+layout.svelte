<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import Trash_2 from 'lucide-svelte/icons/trash-2';

	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import BreadcrumbsBar from '../../BreadcrumbsBar.svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import DialogCloseIcon from '$lib/icons/DialogCloseIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	export let data;
	$: ({ organizationData } = data);

	let isDeletingProject = false;
	let isLoadingDelete = false;

	let tabHighlightPos = '';
	$: if ($page.route.id?.endsWith('/project/[project_id]/action-table')) {
		tabHighlightPos = 'left-0';
	} else if ($page.route.id?.endsWith('/project/[project_id]/knowledge-table')) {
		tabHighlightPos = 'left-1/3';
	} else if ($page.route.id?.endsWith('/project/[project_id]/chat-table')) {
		tabHighlightPos = 'left-2/3';
	}

	$: activeProject = (organizationData?.projects ?? []).find(
		(p) => p.id === $page.params.project_id
	);

	async function handleDeleteProject() {
		if (isLoadingDelete) return;
		isLoadingDelete = true;

		const response = await fetch(`/api/projects/${$page.params.project_id}`, {
			method: 'DELETE'
		});
		const responseBody = await response.json();

		if (!response.ok) {
			toast.error('Error deleting project', {
				description: responseBody.err_message?.message || JSON.stringify(responseBody)
			});
			isLoadingDelete = false;
		} else {
			goto('/project');
		}
	}
</script>

<section class="relative flex flex-col !h-screen">
	<BreadcrumbsBar />

	<div class="relative flex flex-col gap-2 p-6 pt-0 pb-0">
		<div class="flex items-center gap-2 -translate-x-2.5 group">
			<div class="flex items-center justify-center ml-3 p-1.5 bg-secondary/[0.12] rounded-md">
				<AssignmentIcon class="h-[26px] text-secondary" />
			</div>
			<h1 class="font-medium text-xl">
				{PUBLIC_IS_LOCAL === 'false' ? activeProject?.name ?? 'Unknown Project' : 'Default Project'}
			</h1>

			<div
				class="flex items-center gap-2 ml-2 opacity-0 group-hover:opacity-100 transition-opacity"
			>
				<Button
					on:click={() => (isDeletingProject = true)}
					title="Delete Project"
					variant="ghost"
					class="p-0.5 h-min aspect-square rounded-full"
				>
					<Trash_2 class="h-4 text-secondary" />
				</Button>
			</div>
		</div>

		{#if PUBLIC_IS_LOCAL === 'false'}
			<span class="text-[#999] text-xs">Project ID: {$page.params.project_id ?? 'Unknown'}</span>
		{/if}

		<div class="grid grid-cols-3 ml-6 w-fit text-sm font-medium -translate-x-6">
			<a
				href="/project/{$page.params.project_id}/action-table"
				class={`px-6 py-3 ${
					$page.route.id?.endsWith('/project/[project_id]/action-table')
						? 'text-secondary'
						: 'text-[#999]'
				} text-center transition-colors`}
			>
				Action Table
			</a>

			<a
				href="/project/{$page.params.project_id}/knowledge-table"
				class={`px-6 py-3 ${
					$page.route.id?.endsWith('/project/[project_id]/knowledge-table')
						? 'text-secondary'
						: 'text-[#999]'
				} text-center transition-colors`}
			>
				Knowledge Table
			</a>

			<a
				href="/project/{$page.params.project_id}/chat-table"
				class={`px-6 py-3 ${
					$page.route.id?.endsWith('/project/[project_id]/chat-table')
						? 'text-secondary'
						: 'text-[#999]'
				} text-center transition-colors`}
			>
				Chat Table
			</a>

			<div
				class={`absolute bottom-0 ${tabHighlightPos} h-1 w-1/3 bg-secondary data-dark:bg-[#5b7ee5] transition-[left]`}
			/>
		</div>

		<hr class="absolute bottom-0 left-0 w-[calc(100%)] border-[#DDD] data-dark:border-[#0D0E11]" />
	</div>

	<slot />
</section>

<Dialog.Root bind:open={isDeletingProject}>
	<Dialog.Content class="w-[26rem] bg-white data-dark:bg-[#42464e]">
		<DialogPrimitive.Close
			class="absolute top-5 right-5 p-0 flex items-center justify-center h-10 w-10 hover:bg-accent hover:text-accent-foreground rounded-full ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
		>
			<CloseIcon class="w-7" />
			<span class="sr-only">Close</span>
		</DialogPrimitive.Close>

		<div class="flex flex-col items-start gap-2 p-8 pb-10">
			<DialogCloseIcon
				class="mb-1 h-10 [&>path]:fill-red-500 [&>path]:stroke-white data-dark:[&>path]:stroke-[#42464e]"
			/>
			<h3 class="font-bold text-2xl">Are you sure?</h3>
			<p class="text-text/60 text-sm">
				Do you really want to delete project
				<span class="font-medium text-black data-dark:text-white">
					`{activeProject?.name || $page.params.project_id}`
				</span>? This process cannot be undone.
			</p>
		</div>

		<Dialog.Actions class="bg-[#f6f6f6] data-dark:bg-[#303338]">
			<form on:submit|preventDefault={handleDeleteProject} class="flex gap-2">
				<DialogPrimitive.Close asChild let:builder>
					<Button builders={[builder]} variant="link" type="button" class="grow px-6">
						Cancel
					</Button>
				</DialogPrimitive.Close>
				<Button
					type="submit"
					loading={isLoadingDelete}
					variant="destructive"
					class="grow px-6 rounded-full"
				>
					Delete
				</Button>
			</form>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
