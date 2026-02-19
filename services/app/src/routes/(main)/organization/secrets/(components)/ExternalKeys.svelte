<script lang="ts">
	import Fuse from 'fuse.js';
	import { PROVIDERS } from '$lib/constants';
	import type { PageData } from '../$types';

	import { DeleteExtKeyDialog, EditExtKeyDialog } from '.';
	import { Button } from '$lib/components/ui/button';
	import * as Tabs from '$lib/components/ui/tabs';
	import * as Table from '$lib/components/ui/table';
	import InputText from '$lib/components/InputText.svelte';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { organizationData }: { organizationData: PageData['organizationData'] } = $props();

	let searchQuery = $state('');
	let isEditingExtKey = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});
	let isDeletingExtKey = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});

	const filterExtKeys = (providers: string[]) => {
		const fuse = new Fuse(providers, {
			threshold: 0.4,
			includeScore: false
		});
		return searchQuery.trim() ? fuse.search(searchQuery).map((result) => result.item) : providers;
	};
</script>

<Tabs.Content value="external-keys" class="h-1 w-full grow flex-col gap-2 data-[state=active]:flex">
	<div class="flex items-center justify-between">
		<SearchBar
			bind:searchQuery
			isLoadingSearch={false}
			debouncedSearch={async () => {}}
			label="Search"
			placeholder="Search"
			class="w-[12rem]"
		/>

		<PermissionGuard reqOrgRole="ADMIN">
			<Button
				type="button"
				onclick={() => (isEditingExtKey = { open: true, value: null })}
				class="w-fit px-6"
			>
				Add API key
			</Button>
		</PermissionGuard>
	</div>

	<div class="flex h-1 flex-1 grow flex-col overflow-auto rounded-xl border bg-background">
		<Table.Root>
			<Table.Header class="sticky top-0 bg-[#F9FAFB]">
				<Table.Row class="uppercase">
					<Table.Head class="w-1/2 min-w-[300px]">Name</Table.Head>
					<Table.Head class="w-1/2 min-w-[300px]">Value</Table.Head>
					<PermissionGuard reqOrgRole="ADMIN">
						<Table.Head class="w-[160px] min-w-[160px]">Actions</Table.Head>
					</PermissionGuard>
				</Table.Row>
			</Table.Header>
			<Table.Body class="overscroll-y-auto">
				{#if Object.keys(organizationData?.external_keys ?? {}).length > 0}
					{@const extKeys = Object.keys(organizationData?.external_keys ?? {})}
					{#each filterExtKeys(extKeys) as provider}
						<Table.Row>
							<Table.Cell>
								<p class="w-full break-all py-2">
									{PROVIDERS[provider] ?? provider}
								</p>
							</Table.Cell>
							<Table.Cell>
								<InputText
									obfuscate
									readonly
									name="api_key"
									value={organizationData?.external_keys[provider]}
									class="w-full border-0 bg-transparent py-0 pl-0.5"
								/>
							</Table.Cell>
							<PermissionGuard reqOrgRole="ADMIN">
								<Table.Cell>
									<Button
										variant="outline-neutral"
										onclick={() => (isEditingExtKey = { open: true, value: provider })}
										title="Edit API key"
										class="h-7"
									>
										Edit
									</Button>

									<Button
										variant="destructive-init"
										onclick={() => (isDeletingExtKey = { open: true, value: provider })}
										title="Delete API key"
										class="h-7"
									>
										Delete
									</Button>
								</Table.Cell>
							</PermissionGuard>
						</Table.Row>
					{/each}
				{:else}
					<Table.Row>
						<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
							<div class="absolute left-1/2 flex -translate-x-1/2 flex-col">
								<span class="text-lg font-medium">No external keys found</span>
							</div>
						</Table.Cell>
					</Table.Row>
				{/if}
			</Table.Body>
		</Table.Root>
	</div>
</Tabs.Content>

<EditExtKeyDialog {organizationData} bind:isEditingExtKey />
<DeleteExtKeyDialog {organizationData} bind:isDeletingExtKey />
