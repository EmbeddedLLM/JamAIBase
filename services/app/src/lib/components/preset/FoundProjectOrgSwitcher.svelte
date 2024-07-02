<script lang="ts">
	import { activeOrganization } from '$globalStore';
	import type { Organization } from '$lib/types';

	import { Button } from '$lib/components/ui/button';

	export let projectOrg: Organization | undefined;
	export let status = 404;
	export let message = 'Project not found.';
</script>

<div class="flex items-center justify-center mx-4 my-0 h-full">
	<div class="flex flex-col gap-4 max-w-[25rem]">
		<div class="flex items-center">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{status}
			</span>
			<div
				class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
			>
				<h1>{message}</h1>
			</div>
		</div>
		<div class="flex flex-col text-text/60">
			<p>
				Did you mean to go to this project in the
				<span class="font-medium text-black data-dark:text-white">
					`{projectOrg?.organization_name}`
				</span>
				organization?
			</p>
		</div>
		<div class="flex items-center justify-between">
			<Button
				on:click={() => {
					if (projectOrg) {
						$activeOrganization = projectOrg;
					}
					window.location.reload();
				}}
				variant="secondary"
				type="button"
				class="px-6 rounded-full"
			>
				Go to organization
			</Button>
		</div>
	</div>
</div>
