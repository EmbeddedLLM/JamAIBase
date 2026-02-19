<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { onMount, tick } from 'svelte';
	import { enhance } from '$app/forms';
	import { activeOrganization } from '$globalStore';
	import type { Project } from '$lib/types';
	import type { PageData } from '../$types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Table from '$lib/components/ui/table';
	import { Switch } from '$lib/components/ui/switch';
	import InputText from '$lib/components/InputText.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SearchIcon from '$lib/icons/SearchIcon.svelte';
	import Checkbox from '$lib/components/Checkbox.svelte';

	let {
		orgSecretsPromise,
		isEditingOrgSecret = $bindable()
	}: {
		orgSecretsPromise: PageData['orgSecrets'];
		isEditingOrgSecret: { open: boolean; value: string | null };
	} = $props();

	let orgSecrets = $state<NonNullable<Awaited<PageData['orgSecrets']>['data']>>([]);
	let selectedSecret = $derived(orgSecrets.find((s) => s.name === isEditingOrgSecret.value));

	$effect(() => {
		if (orgSecretsPromise instanceof Promise) {
			orgSecretsPromise
				.then((value) => {
					orgSecrets = value.data ?? [];
				})
				.catch((err) => {
					console.error(err);
					orgSecrets = [];
				});
		} else {
			orgSecrets = orgSecretsPromise;
		}
	});

	let loadingSave = $state(false);

	let enableSelectProject = $state(false);
	let searchQuery = $state('');
	let isLoadingSearch = $state(false);
	let allowedProjects = $state<string[]>([]);

	$effect(() => {
		if (isEditingOrgSecret.value) {
			if (selectedSecret?.allowed_projects) {
				enableSelectProject = true;
				allowedProjects = selectedSecret.allowed_projects;
			} else {
				enableSelectProject = false;
				allowedProjects = [];
			}
		} else {
			enableSelectProject = false;
			allowedProjects = [];
		}
	});

	let fetchController: AbortController | null = null;
	let orgProjects: Project[] = $state([]);
	let loadingProjectsError: { status: number; message: string } | null = $state(null);
	let isLoadingProjects = $state(true);
	let isLoadingMoreProjects = $state(false);
	let moreProjectsFinished = false; //FIXME: Bandaid fix for infinite loop caused by loading circle
	let currentOffset = 0;
	const limit = 50;

	async function getProjects() {
		if (!$activeOrganization) return;
		if (!isLoadingProjects) {
			isLoadingMoreProjects = true;
		}

		fetchController = new AbortController();

		try {
			const searchParams = new URLSearchParams([
				['offset', currentOffset.toString()],
				['limit', limit.toString()],
				// ['order_by', $sortOptions.orderBy],
				// ['order_ascending', $sortOptions.order === 'asc' ? 'true' : 'false'],
				['organization_id', $activeOrganization.id]
			]);

			if (searchQuery.trim() !== '') {
				searchParams.append('search_query', searchQuery.trim());
			}

			const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/projects/list?${searchParams}`, {
				credentials: 'same-origin',
				signal: fetchController.signal
			});
			currentOffset += limit;

			if (response.status == 200) {
				const moreProjects = await response.json();
				if (moreProjects.items.length) {
					orgProjects = [...orgProjects, ...moreProjects.items];
				} else {
					//* Finished loading oldest conversation
					moreProjectsFinished = true;
				}
			} else {
				const responseBody = await response.json();
				console.error(responseBody);
				toast.error('Failed to fetch projects', {
					id: responseBody?.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody?.message || JSON.stringify(responseBody),
						requestID: responseBody?.request_id
					}
				});
				loadingProjectsError = {
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

		isLoadingProjects = false;
		isLoadingMoreProjects = false;
	}

	async function refetchProjects() {
		fetchController?.abort('Duplicate');
		orgProjects = [];
		currentOffset = 0;
		moreProjectsFinished = false;
		await tick();
		await getProjects();
		isLoadingSearch = false;
	}

	onMount(() => {
		refetchProjects();
	});

	const debouncedSearchProjects = debounce((e) => {
		searchQuery = e.target?.value;
		isLoadingSearch = true;
		refetchProjects();
	}, 300);

	const scrollHandler = async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollHeight - target.clientHeight - target.scrollTop;
		const LOAD_THRESHOLD = 1000;

		if (
			orgProjects.length > 0 &&
			offset < LOAD_THRESHOLD &&
			!isLoadingProjects &&
			!moreProjectsFinished
		) {
			fetchController?.abort('Duplicate');
			await getProjects();
		}
	};
</script>

<Dialog.Root
	bind:open={
		() => isEditingOrgSecret.open, (v) => (isEditingOrgSecret = { ...isEditingOrgSecret, open: v })
	}
>
	<Dialog.Content class="h-fit max-h-[90vh] w-[clamp(0px,35rem,100%)]">
		<Dialog.Header>
			<Dialog.Title>{isEditingOrgSecret.value ? 'Edit' : 'Add'} secret</Dialog.Title>
		</Dialog.Header>

		<form
			method="POST"
			id="updateOrgSecret"
			use:enhance={({ formData, cancel }) => {
				loadingSave = true;

				if (!isEditingOrgSecret.value) {
					formData.append('new', 'true');
				}

				if (enableSelectProject) {
					formData.append('allowed_projects', JSON.stringify(allowedProjects));
				}

				if (!formData.get('name')) {
					cancel();
				}

				return async ({ update, result }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error('Error updating organization secrets', {
							id: data?.error || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						isEditingOrgSecret = { ...isEditingOrgSecret, open: false };
					}

					loadingSave = false;
					update({ reset: false });
				};
			}}
			action="?/update-org-secret"
			class="flex grow flex-col gap-3 overflow-auto py-3"
		>
			<div class="space-y-1 px-4 sm:px-6">
				<Label required id="name">Name</Label>
				<Input required name="name" type="text" value={selectedSecret?.name} />
			</div>

			<div class="space-y-1 px-4 sm:px-6">
				<Label required id="value">Value</Label>
				<Input required name="value" type="text" />
			</div>

			<div class="flex justify-between space-y-1 px-4 sm:px-6">
				<div>
					<Label class="text-[#1D2939]">Restrict project access</Label>
					<p class="text-sm">Choose which projects can access it</p>
				</div>

				<Switch
					id="project-select"
					name="project-select"
					class=""
					bind:checked={enableSelectProject}
				/>
			</div>

			{#if enableSelectProject}
				<div class="space-y-2 px-4 sm:px-6">
					<InputText
						oninput={debouncedSearchProjects}
						type="search"
						placeholder="Search projects"
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

					<div
						onscroll={debounce(scrollHandler, 300)}
						class="flex h-full max-h-72 flex-1 grow flex-col overflow-auto rounded-xl border bg-background"
					>
						<Table.Root>
							<Table.Header class="sticky top-0 bg-[#F9FAFB]">
								<Table.Row class="uppercase">
									<Table.Head class="h-[unset] w-[25px] px-0 py-2"></Table.Head>
									<Table.Head class="h-[unset] w-[200px] px-0 py-2 uppercase">
										Project Name
									</Table.Head>
								</Table.Row>
							</Table.Header>
							<Table.Body class="overscroll-y-auto">
								{#if orgProjects.length > 0}
									{#each orgProjects as orgProject}
										<Table.Row>
											<Table.Cell class="w-[25px] px-0 py-2">
												<div class="flex items-center justify-center">
													<Checkbox
														bind:checked={
															() => allowedProjects.includes(orgProject.id),
															(e) => {
																allowedProjects = e
																	? [...allowedProjects, orgProject.id]
																	: allowedProjects.filter((id) => id !== orgProject.id);
															}
														}
														class="h-4 w-4 sm:h-[18px] sm:w-[18px] [&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[1px] sm:[&>svg]:h-3.5 sm:[&>svg]:w-3.5"
													/>
												</div>
											</Table.Cell>
											<Table.Cell class="px-0 py-2">
												<p class="w-full break-all">
													{orgProject.name}
												</p>
											</Table.Cell>
										</Table.Row>
									{/each}

									{#if isLoadingMoreProjects}
										<Table.Row>
											<Table.Cell colspan={2} class="h-16 w-full">
												<LoadingSpinner class="mx-auto text-secondary" />
											</Table.Cell>
										</Table.Row>
									{/if}
								{:else if isLoadingSearch || isLoadingProjects}
									<Table.Row>
										<Table.Cell colspan={2} class="h-16 w-full">
											<LoadingSpinner class="mx-auto text-secondary" />
										</Table.Cell>
									</Table.Row>
								{:else}
									<Table.Row>
										<Table.Cell colspan={2} class="h-16 w-full">
											<p class="mx-auto text-center">No projects found</p>
										</Table.Cell>
									</Table.Row>
								{/if}
							</Table.Body>
						</Table.Root>
					</div>
				</div>
			{/if}
		</form>

		<Dialog.Actions>
			<div class="flex justify-end gap-2">
				<Button
					type="button"
					onclick={() => (isEditingOrgSecret = { ...isEditingOrgSecret, open: false })}
					variant="link"
				>
					Cancel
				</Button>
				<Button form="updateOrgSecret" type="submit" loading={loadingSave} disabled={loadingSave}>
					{isEditingOrgSecret.value ? 'Edit' : 'Add'} secret
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
