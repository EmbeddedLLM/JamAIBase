<script lang="ts">
	import { hasPermission } from '$lib/utils';

	import { ExternalKeys, OrgSecrets } from './(components)';
	import * as Tabs from '$lib/components/ui/tabs';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>Secrets - Organization</title>
</svelte:head>

<div class="grow px-4 py-3">
	<Tabs.Root
		value={hasPermission(data.user, data.ossMode, data.organizationData?.id ?? '', '', 'MEMBER')
			? 'env-vars'
			: 'external-keys'}
		class="flex h-full flex-col items-start rounded-lg bg-white p-2"
	>
		<Tabs.List class="h-[unset] gap-0.5 bg-[unset] p-0">
			<PermissionGuard reqOrgRole="MEMBER">
				<Tabs.Trigger
					value="env-vars"
					class="rounded-lg border border-transparent data-[state=active]:border-[#FFD8DF] data-[state=active]:bg-[#FFEFF2] data-[state=active]:text-[#950048] data-[state=active]:shadow-[unset]"
				>
					Environment Variables
				</Tabs.Trigger>
			</PermissionGuard>
			<Tabs.Trigger
				value="external-keys"
				class="rounded-lg border border-transparent data-[state=active]:border-[#FFD8DF] data-[state=active]:bg-[#FFEFF2] data-[state=active]:text-[#950048] data-[state=active]:shadow-[unset]"
			>
				External Keys
			</Tabs.Trigger>
		</Tabs.List>

		<PermissionGuard reqOrgRole="MEMBER">
			<OrgSecrets orgSecrets={data.orgSecrets} />
		</PermissionGuard>

		<ExternalKeys organizationData={data.organizationData} />
	</Tabs.Root>
</div>
