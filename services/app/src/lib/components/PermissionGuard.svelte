<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { page } from '$app/state';
	import { activeOrganization, activeProject } from '$globalStore';
	import type { userRoles } from '$lib/constants';
	import type { Snippet } from 'svelte';
	import type { LayoutData } from '../../routes/$types';

	let {
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
		children: Snippet;
		deniedMessage?: Snippet;
	} = $props();

	const roleHierarchy = {
		GUEST: 1,
		MEMBER: 2,
		ADMIN: 3
	} as Record<(typeof userRoles)[number], number>;

	function hasPermission() {
		if (page.data.ossMode) return true;

		const orgRole = (page.data as LayoutData).user?.org_memberships.find(
			(org) => org.organization_id === $activeOrganization?.id
		)?.role;
		const projRole = (page.data as LayoutData).user?.proj_memberships.find(
			(proj) => proj.project_id === $activeProject?.id
		)?.role;

		const userOrgLevel = roleHierarchy[orgRole ?? 'GUEST'];
		const userProjLevel = roleHierarchy[projRole ?? 'GUEST'];

		const reqOrgLevel = roleHierarchy[reqOrgRole ?? 'GUEST'];
		const reqProjLevel = roleHierarchy[reqProjRole ?? 'GUEST'];
		if (
			!reqOrgRole ||
			userOrgLevel >= reqOrgLevel ||
			!reqProjRole ||
			userProjLevel >= reqProjLevel
		) {
			return true;
		} else {
			return false;
		}
	}
</script>

{#if hasPermission()}
	{@render children()}
{:else}
	{@render deniedMessage?.()}
{/if}
