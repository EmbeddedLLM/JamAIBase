<script lang="ts">
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import { activeOrganization, activeProject } from '$globalStore';
	import type { userRoles } from '$lib/constants';
	import { hasPermission } from '$lib/utils';

	let {
		projectId,
		reqOrgRole,
		reqProjRole,
		children,
		deniedMessage
	}: (
		| {
				reqOrgRole: (typeof userRoles)[number];
				reqProjRole?: (typeof userRoles)[number];
		  }
		| {
				reqOrgRole?: (typeof userRoles)[number];
				reqProjRole: (typeof userRoles)[number];
		  }
	) & {
		projectId?: string;
		children: Snippet;
		deniedMessage?: Snippet;
	} = $props();
</script>

{#if hasPermission(page.data.user, page.data.ossMode, page.data.organizationData?.id ?? $activeOrganization?.id ?? '', projectId ?? $activeProject?.id ?? '', reqOrgRole, reqProjRole)}
	{@render children()}
{:else}
	{@render deniedMessage?.()}
{/if}
