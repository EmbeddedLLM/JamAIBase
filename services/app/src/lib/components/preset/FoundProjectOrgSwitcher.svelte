<script lang="ts">
	/* Hooks API proxy returns organization ID */
	import { tick } from 'svelte';
	import { activeOrganization } from '$globalStore';
	import type { OrganizationReadRes } from '$lib/types';

	import { Button } from '$lib/components/ui/button';

	interface Props {
		projectOrg: OrganizationReadRes | undefined;
		status?: number;
		message?: string;
	}

	let { projectOrg, status = 404, message = 'Project not found.' }: Props = $props();
</script>

<div class="my-0 flex h-full items-center justify-center px-8">
	<div class="flex max-w-[25rem] flex-col gap-4">
		<div class="flex items-center">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{status}
			</span>
			<div
				class="ml-4 flex min-h-10 items-center border-l border-[#ccc] pl-4 data-dark:border-[#666]"
			>
				<h1>{message}</h1>
			</div>
		</div>
		<div class="flex flex-col text-text/60">
			<p>
				Did you mean to go to this project in the
				<span class="font-medium text-black data-dark:text-white">
					`{projectOrg?.name}`
				</span>
				organization?
			</p>
		</div>
		<div class="flex items-center justify-between">
			<Button
				onclick={async () => {
					if (projectOrg) {
						activeOrganization.setOrgCookie(projectOrg.id);
					}
					await tick();
					window.location.reload();
				}}
				type="button"
				class="px-6"
			>
				Go to organization
			</Button>
		</div>
	</div>
</div>
