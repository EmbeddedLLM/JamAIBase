<script lang="ts">
	import Fuse from 'fuse.js';
	import { formatDistanceToNow } from 'date-fns';
	import type { PageData } from '../$types';

	import { DeleteOrgSecretDialog, EditOrgSecretDialog } from '.';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Tabs from '$lib/components/ui/tabs';
	import * as Table from '$lib/components/ui/table';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';

	let { orgSecrets }: { orgSecrets: PageData['orgSecrets'] } = $props();

	let searchQuery = $state('');
	let isEditingOrgSecret = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});
	let isDeletingOrgSecret = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});

	const filterOrgSecrets = (secrets: NonNullable<Awaited<PageData['orgSecrets']>['data']>) => {
		const fuse = new Fuse(secrets, {
			keys: ['name'],
			threshold: 0.4,
			includeScore: false
		});
		return searchQuery.trim() ? fuse.search(searchQuery).map((result) => result.item) : secrets;
	};
</script>

<Tabs.Content value="env-vars" class="h-1 w-full grow flex-col gap-2 data-[state=active]:flex">
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
				onclick={() => (isEditingOrgSecret = { open: true, value: null })}
				class="w-fit px-6"
			>
				Add secret
			</Button>
		</PermissionGuard>
	</div>

	<div class="flex h-1 flex-1 grow flex-col overflow-auto rounded-xl border bg-background">
		<Table.Root>
			<Table.Header class="sticky top-0 bg-[#F9FAFB]">
				<Table.Row class="uppercase">
					<Table.Head class="w-[250px] min-w-[250px]">Name</Table.Head>
					<Table.Head class="w-[100px]">Value</Table.Head>
					<Table.Head class="w-[150px] min-w-[140px]">Last updated</Table.Head>
					<Table.Head class="w-[200px] min-w-[200px]">Allowed projects</Table.Head>
					<PermissionGuard reqOrgRole="ADMIN">
						<Table.Head class="w-[160px] min-w-[160px]">Actions</Table.Head>
					</PermissionGuard>
				</Table.Row>
			</Table.Header>
			<Table.Body class="overscroll-y-auto">
				{#await orgSecrets}
					{#each Array(6) as _}
						<Table.Row>
							<Table.Cell colspan={100} class="p-1.5">
								<Skeleton class="h-[3.75rem] w-full" />
							</Table.Cell>
						</Table.Row>
					{/each}
				{:then orgSecrets}
					{#if orgSecrets.data}
						{@const filteredOrgSecrets = filterOrgSecrets(orgSecrets.data)}
						{#if filteredOrgSecrets.length > 0}
							{#each filteredOrgSecrets as orgSecret}
								<Table.Row>
									<Table.Cell>
										<p class="w-full break-all py-2">
											{orgSecret.name}
										</p>
									</Table.Cell>
									<Table.Cell>
										<InputText
											obfuscate={false}
											readonly
											name="org_secret"
											value={orgSecret.value}
											class="w-full border-0 bg-transparent py-0 pl-0.5"
										/>
									</Table.Cell>
									<Table.Cell>
										{formatDistanceToNow(new Date(orgSecret.updated_at), { addSuffix: true })}
									</Table.Cell>
									<Table.Cell>
										{#if orgSecret.allowed_projects}
											{#if orgSecret.allowed_projects.length > 0}
												<p>{orgSecret.allowed_projects.join(', ')}</p>
											{:else}
												<p class="w-full break-all py-2">No projects</p>
											{/if}
										{:else}
											<p class="w-full break-all py-2">All projects</p>
										{/if}
									</Table.Cell>
									<PermissionGuard reqOrgRole="ADMIN">
										<Table.Cell class="min-w-[165px] max-w-[165px]">
											<Button
												variant="outline-neutral"
												onclick={() => (isEditingOrgSecret = { open: true, value: orgSecret.name })}
												title="Edit env value"
												class="h-7"
											>
												Edit
											</Button>

											<Button
												variant="destructive-init"
												onclick={() =>
													(isDeletingOrgSecret = { open: true, value: orgSecret.name })}
												title="Delete env"
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
										<span class="text-lg font-medium">No environment variables found</span>
									</div>
								</Table.Cell>
							</Table.Row>
						{/if}
					{:else}
						<Table.Row>
							<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
								<div class="absolute left-1/2 flex w-[26rem] -translate-x-1/2 flex-col text-center">
									<span class="text-lg font-medium">
										Error fetching organization environment variables
									</span>
									<span class="text-sm">
										{orgSecrets?.message.message || JSON.stringify(orgSecrets?.message)}
									</span>
								</div>
							</Table.Cell>
						</Table.Row>
					{/if}
				{/await}
			</Table.Body>
		</Table.Root>
	</div>
</Tabs.Content>

<EditOrgSecretDialog bind:isEditingOrgSecret orgSecretsPromise={orgSecrets} />
<DeleteOrgSecretDialog bind:isDeletingOrgSecret />
