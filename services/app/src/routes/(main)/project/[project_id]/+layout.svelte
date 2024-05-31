<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { page } from '$app/stores';

	import AssignmentIcon from '$lib/icons/AssignmentIcon.svelte';
	import BreadcrumbsBar from '../../BreadcrumbsBar.svelte';

	const { PUBLIC_IS_LOCAL } = env;

	export let data;
	$: ({ organizationData } = data);

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
</script>

<section class="relative flex flex-col !h-screen">
	<BreadcrumbsBar />

	<div class="relative flex flex-col gap-2 p-6 pt-0 pb-0">
		<div class="flex items-center gap-2 -translate-x-2.5">
			<div class="flex items-center justify-center ml-3 p-1.5 bg-secondary/[0.12] rounded-md">
				<AssignmentIcon class="h-[26px] text-secondary" />
			</div>
			<h1 class="font-medium text-xl">
				{PUBLIC_IS_LOCAL === 'false' ? activeProject?.name ?? 'Unknown' : 'Default Project'}
			</h1>
		</div>

		{#if PUBLIC_IS_LOCAL === 'false'}
			<span class="text-[#999] text-xs">Project ID: {activeProject?.id ?? 'Unknown'}</span>
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
