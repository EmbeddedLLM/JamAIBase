<script lang="ts">
	import { PROVIDERS } from '$lib/constants';

	import { DeleteExtKeyDialog, EditExtKeyDialog } from './(components)';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';

	let { data } = $props();
	let { organizationData } = $derived(data);

	let isEditingExtKey = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});
	let isDeletingExtKey = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});
</script>

<svelte:head>
	<title>Secrets - Organization</title>
</svelte:head>

<div class="overflow-auto px-4 py-4 sm:px-8 sm:py-6">
	<section data-testid="org-external-keys" class="mb-12">
		<h2 class="mb-4 text-sm font-medium text-[#667085]">EXTERNAL API KEYS</h2>

		<PermissionGuard reqOrgRole="ADMIN">
			<div class="flex flex-col gap-1 overflow-auto">
				<div
					role="grid"
					style="grid-template-rows: min-content;"
					class="relative grid h-auto min-h-0 min-w-fit rounded-lg border border-[#F2F4F7] bg-white px-2 data-dark:bg-[#484C55]"
				>
					<div
						role="row"
						style="grid-template-columns: 200px minmax(24rem, 1fr) 140px;"
						class="sticky top-0 z-20 grid h-[50px] bg-white text-sm font-medium data-dark:bg-[#484C55]"
					>
						<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">Provider</div>
						<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">API Key</div>
						<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]"></div>
					</div>
				</div>

				{#if Object.keys(organizationData?.external_keys ?? {}).length > 0}
					{@const extKeys = Object.keys(organizationData?.external_keys ?? {})}
					<div
						role="grid"
						style="grid-template-rows: repeat({extKeys.length ?? 0}, min-content);"
						class="relative grid h-auto min-h-0 min-w-fit grow overflow-y-auto overflow-x-visible rounded-lg border border-[#F2F4F7] bg-white px-2 data-dark:bg-[#484C55]"
					>
						{#each extKeys as provider}
							<div
								role="row"
								style="grid-template-columns: 200px minmax(24rem, 1fr) 140px;"
								class="relative grid min-h-[50px] text-sm [&>hr]:last:hidden"
							>
								<div role="gridcell" class="flex items-center justify-start gap-1 px-2">
									<p class="w-full break-all py-2">
										{PROVIDERS[provider] ?? provider}
									</p>
								</div>

								<div role="gridcell" class="flex items-center px-2">
									<InputText
										obfuscate
										readonly
										name="api_key"
										value={organizationData?.external_keys[provider]}
										class="w-full border-0 bg-transparent py-0 pl-0.5"
									/>
								</div>

								<div role="gridcell" class="flex items-center justify-start gap-1 px-2">
									<Button
										onclick={() => (isEditingExtKey = { open: true, value: provider })}
										title="Edit API key"
										class="h-7"
									>
										Edit
									</Button>

									<Button
										variant="destructive"
										onclick={() => (isDeletingExtKey = { open: true, value: provider })}
										title="Delete API key"
										class="h-7"
									>
										Delete
									</Button>
								</div>
								<!-- <hr class="absolute bottom-0 left-0 right-0 -mx-2 border-[#F2F4F7]" /> -->
							</div>
						{/each}
					</div>
				{:else}
					<div
						class="relative flex h-24 min-h-0 min-w-fit grow items-center justify-center overflow-auto rounded-lg border border-[#F2F4F7] bg-white px-2 data-dark:bg-[#484C55]"
					>
						<div
							role="row"
							style="grid-template-columns: 200px minmax(24rem, 1fr) 240px 170px;"
							class="relative grid min-h-[50px] text-sm [&>hr]:last:hidden"
						>
							<div class="col-span-full flex items-center justify-center">
								<p class="text-sm italic">No external keys have been added to this organization</p>
							</div>
						</div>
					</div>
				{/if}
			</div>

			<div class="mb-8 mt-2 flex w-full flex-col gap-3">
				<Button
					type="button"
					onclick={() => (isEditingExtKey = { open: true, value: null })}
					class="w-fit px-6"
				>
					Add API Key
				</Button>
			</div>

			{#snippet deniedMessage()}
				<div
					class="flex h-48 w-[clamp(0px,100%,600px)] items-center justify-center rounded-lg bg-white p-4 text-center"
				>
					<p>You need to be an Admin to manage external keys in your organization</p>
				</div>
			{/snippet}
		</PermissionGuard>
	</section>
</div>

<EditExtKeyDialog {organizationData} bind:isEditingExtKey />
<DeleteExtKeyDialog {organizationData} bind:isDeletingExtKey />
