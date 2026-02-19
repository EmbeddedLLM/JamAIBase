<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { onMount, tick } from 'svelte';
	import { activeProject } from '$globalStore';
	import { ROLE_COLORS } from '$lib/constants';
	import type { VerificationCodeRead } from '$lib/types';

	import { RevokeProjInviteDialog } from '.';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Tabs from '$lib/components/ui/tabs';
	import * as Table from '$lib/components/ui/table';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import InputText from '$lib/components/InputText.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import CopyIcon2 from '$lib/icons/CopyIcon2.svelte';
	import SorterSelect from '$lib/components/preset/SorterSelect.svelte';

	let {
		isInvitingUser = $bindable()
	}: {
		isInvitingUser: boolean;
	} = $props();

	let searchQuery = $state('');
	let isLoadingSearch = $state(false);
	let revokingInvite: { open: boolean; value: VerificationCodeRead | null } = $state({
		open: false,
		value: null
	});

	let fetchController: AbortController | null = null;
	let projectInvites: VerificationCodeRead[] = $state([]);
	let loadingInvitesError: { status: number; message: any } | null = $state(null);
	let isLoadingInvites = $state(true);
	let isLoadingMoreInvites = $state(false);
	let moreInvitesFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	let sortOptions = $state<{
		orderBy: string;
		order: 'asc' | 'desc';
	}>({ orderBy: 'updated_at', order: 'desc' });
	const sortableFields = [
		{ id: 'id', title: 'ID' },
		{ id: 'name', title: 'Name' },
		{ id: 'created_at', title: 'Date created' },
		{ id: 'updated_at', title: 'Date modified' }
	];

	async function getProjectInvites() {
		if (!$activeProject) return;
		if (!isLoadingInvites) {
			isLoadingMoreInvites = true;
		}

		fetchController = new AbortController();

		try {
			const searchParams = new URLSearchParams([
				['offset', currentOffset.toString()],
				['limit', limit.toString()],
				['order_by', sortOptions.orderBy],
				['order_ascending', sortOptions.order === 'asc' ? 'true' : 'false'],
				['project_id', $activeProject.id]
			]);

			if (searchQuery.trim() !== '') {
				searchParams.append('search_query', searchQuery.trim());
				searchParams.append('search_columns', 'name');
				searchParams.append('search_columns', 'user_email');
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/projects/invites/list?${searchParams}`,
				{
					credentials: 'same-origin',
					signal: fetchController.signal
				}
			);
			currentOffset += limit;

			if (response.status == 200) {
				const moreProjects = await response.json();
				if (moreProjects.items.length) {
					projectInvites = [...projectInvites, ...moreProjects.items];
				} else {
					//* Finished loading oldest conversation
					moreInvitesFinished = true;
				}
			} else {
				const responseBody = await response.json();
				console.error(responseBody);
				toast.error('Failed to fetch project invites', {
					id: responseBody?.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody?.message || JSON.stringify(responseBody),
						requestID: responseBody?.request_id
					}
				});
				loadingInvitesError = {
					status: response.status,
					message: responseBody
				};
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Navigated' && err !== 'Duplicate') {
				console.error(err);
			}
		}

		isLoadingInvites = false;
		isLoadingMoreInvites = false;
	}

	export async function refetchProjectInvites() {
		fetchController?.abort('Duplicate');
		projectInvites = [];
		currentOffset = 0;
		moreInvitesFinished = false;
		isLoadingInvites = true;
		await tick();
		await getProjectInvites();
		isLoadingSearch = false;
	}

	onMount(() => {
		refetchProjectInvites();
	});

	const debouncedSearchInvites = debounce((e) => {
		searchQuery = e.target?.value;
		isLoadingSearch = true;
		refetchProjectInvites();
	}, 300);

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (
			projectInvites.length > 0 &&
			offset < LOAD_THRESHOLD &&
			!isLoadingInvites &&
			!moreInvitesFinished
		) {
			fetchController?.abort('Duplicate');
			await getProjectInvites();
		}
	};
</script>

<Tabs.Content value="invitations" class="h-1 w-full grow flex-col gap-2 data-[state=active]:flex">
	<div class="flex items-center justify-between">
		<div class="flex w-min items-center gap-2">
			<InputText
				oninput={debouncedSearchInvites}
				type="search"
				placeholder="Search"
				class="h-9 w-[12rem] pl-8 placeholder:not-italic placeholder:text-[#98A2B3]"
			>
				{#snippet leading()}
					{#if isLoadingSearch}
						<div class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
							<LoadingSpinner class="h-3" />
						</div>
					{:else}
						<SearchIcon
							class="pointer-events-none absolute left-3 top-1/2 h-3 -translate-y-1/2 text-[#667085]"
						/>
					{/if}
				{/snippet}
			</InputText>

			<SorterSelect
				bind:sortOptions
				{sortableFields}
				refetchTables={refetchProjectInvites}
				class="w-min min-w-[unset]"
			/>
		</div>

		<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
			<Button type="button" onclick={() => (isInvitingUser = true)} class="w-fit px-6">
				Invite member
			</Button>
		</PermissionGuard>
	</div>

	<div
		onscroll={debounce(scrollHandler, 300)}
		class="flex h-1 flex-1 grow flex-col overflow-auto rounded-xl border bg-background"
	>
		<Table.Root>
			<Table.Header class="sticky top-0 bg-[#F9FAFB]">
				<Table.Row class="uppercase">
					<Table.Head class="w-[200px] min-w-[200px]">Email</Table.Head>
					<Table.Head class="w-[110px] min-w-[110px]">Role</Table.Head>
					<Table.Head class="w-[120px] min-w-[120px]">Created At</Table.Head>
					<Table.Head class="w-[120px] min-w-[120px]">Updated At</Table.Head>
					<Table.Head class="w-[120px] min-w-[120px]">Used At</Table.Head>
					<Table.Head class="w-[120px] min-w-[120px]">Revoked At</Table.Head>
					<Table.Head class="w-[120px] min-w-[120px]">Expires At</Table.Head>
					<Table.Head class="w-[205px] min-w-[205px]">Invitation Code</Table.Head>
					<Table.Head class="w-[50px]">Action</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body class="overscroll-y-auto">
				{#if isLoadingInvites}
					{#each Array(6) as _}
						<Table.Row>
							<Table.Cell colspan={100} class="p-1.5">
								<Skeleton class="h-[3.75rem] w-full" />
							</Table.Cell>
						</Table.Row>
					{/each}
				{:else if !loadingInvitesError}
					{#if projectInvites.length > 0}
						{#each projectInvites as projectInvite}
							<Table.Row>
								<Table.Cell>
									<div class="flex items-center gap-2">
										<p
											title={projectInvite.user_email}
											class="line-clamp-1 break-all text-[#A62050]"
										>
											{projectInvite.user_email}
										</p>
									</div>
									<!-- <span
											title={projectInvite.user.email}
											class="line-clamp-1 break-all text-[#98A2B3]"
										>
											{projectInvite.user.email}
										</span> -->
								</Table.Cell>
								<Table.Cell>
									{#if projectInvite.role}
										<span
											style:background={`${ROLE_COLORS[projectInvite.role]}32`}
											class="inline-flex items-center justify-center gap-x-1 rounded-lg bg-[#E26F64]/20 px-2 text-xs font-medium uppercase text-black"
										>
											<span
												style:color={`${ROLE_COLORS[projectInvite.role]}`}
												class="flex text-xl text-[#E26F64]">•</span
											>
											{projectInvite.role}</span
										>
									{:else}
										-
									{/if}
								</Table.Cell>
								<Table.Cell>
									{new Date(projectInvite.created_at).toLocaleString(undefined, {
										month: 'short',
										day: 'numeric',
										year: 'numeric',
										hour: '2-digit',
										minute: '2-digit',
										second: '2-digit'
									})}
								</Table.Cell>
								<Table.Cell>
									{new Date(projectInvite.updated_at).toLocaleString(undefined, {
										month: 'short',
										day: 'numeric',
										year: 'numeric',
										hour: '2-digit',
										minute: '2-digit',
										second: '2-digit'
									})}
								</Table.Cell>
								<Table.Cell>
									{#if projectInvite.used_at}
										{new Date(projectInvite.used_at).toLocaleString(undefined, {
											month: 'short',
											day: 'numeric',
											year: 'numeric',
											hour: '2-digit',
											minute: '2-digit',
											second: '2-digit'
										})}
									{:else}
										-
									{/if}
								</Table.Cell>
								<Table.Cell>
									{#if projectInvite.revoked_at}
										{new Date(projectInvite.revoked_at).toLocaleString(undefined, {
											month: 'short',
											day: 'numeric',
											year: 'numeric',
											hour: '2-digit',
											minute: '2-digit',
											second: '2-digit'
										})}
									{:else}
										-
									{/if}
								</Table.Cell>
								<Table.Cell>
									{#if projectInvite.expiry}
										{new Date(projectInvite.expiry).toLocaleString(undefined, {
											month: 'short',
											day: 'numeric',
											year: 'numeric',
											hour: '2-digit',
											minute: '2-digit',
											second: '2-digit'
										})}
									{:else}
										-
									{/if}
								</Table.Cell>
								<Table.Cell>
									<div class="flex w-min items-center gap-1.5 rounded-lg bg-[#F2F4F7] px-2 py-1.5">
										{projectInvite.id}

										<Button
											variant="ghost"
											aria-label="Copy invite code"
											onclick={() => {
												navigator.clipboard.writeText(projectInvite.id);
												toast.success('Invite code copied to clipboard', {
													id: 'invite-code-copied'
												});
											}}
											class="relative aspect-square h-6 rounded-full p-[1px] text-muted-foreground hover:bg-white"
										>
											<CopyIcon2 class="absolute h-5" />
										</Button>
									</div>
								</Table.Cell>
								<Table.Cell class="min-w-[165px] max-w-[165px]">
									<Button
										variant="destructive-init"
										disabled={!!projectInvite.used_at || !!projectInvite.revoked_at}
										onclick={() => (revokingInvite = { open: true, value: projectInvite })}
										title="Revoke invite"
										class="h-7"
									>
										Revoke
									</Button>
								</Table.Cell>
							</Table.Row>
						{/each}

						{#if isLoadingMoreInvites}
							<Table.Row>
								<Table.Cell colspan={999} class="h-12 w-full">
									<LoadingSpinner class="mx-auto text-secondary" />
								</Table.Cell>
							</Table.Row>
						{/if}
					{:else if isLoadingSearch}
						<div
							class="sticky left-1/2 flex h-64 -translate-x-1/2 items-center justify-center gap-2 text-center"
						>
							<div class="absolute flex w-80 flex-col">
								<LoadingSpinner class="mx-auto text-secondary" />
							</div>
						</div>
					{:else}
						<Table.Row>
							<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
								<div class="absolute left-1/2 flex -translate-x-1/2 flex-col">
									<span class="text-lg font-medium">No project invites found</span>
								</div>
							</Table.Cell>
						</Table.Row>
					{/if}
				{:else}
					<Table.Row>
						<Table.Cell colspan={999} class="pointer-events-none relative h-64 w-full">
							<div class="absolute left-1/2 flex w-[26rem] -translate-x-1/2 flex-col text-center">
								<span class="text-lg font-medium"> Error fetching project invites </span>
								<span class="text-sm">
									{loadingInvitesError?.message.message ||
										JSON.stringify(loadingInvitesError?.message)}
								</span>
							</div>
						</Table.Cell>
					</Table.Row>
				{/if}
			</Table.Body>
		</Table.Root>
	</div>
</Tabs.Content>

<RevokeProjInviteDialog {refetchProjectInvites} bind:revokingInvite />
