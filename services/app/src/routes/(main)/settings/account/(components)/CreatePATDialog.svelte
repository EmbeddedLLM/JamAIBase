<script lang="ts">
	import { enhance } from '$app/forms';
	import { Check } from '@lucide/svelte';
	import { DateFormatter, getLocalTimeZone, today, type DateValue } from '@internationalized/date';
	import Fuse from 'fuse.js';
	import { getLocale } from '$lib/paraglide/runtime';
	import type { PageData } from '../$types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Calendar } from '$lib/components/ui/calendar';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Popover from '$lib/components/ui/popover';
	import InputText from '$lib/components/InputText.svelte';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';

	const df = new DateFormatter(getLocale(), {
		dateStyle: 'long'
	});

	let { isCreatingPAT = $bindable(), user }: { isCreatingPAT: boolean; user: PageData['user'] } =
		$props();

	let selectedExpiry = $state<DateValue>();
	let selectedProject = $state('');
	let selectedProjectData = $derived((user?.projects ?? []).find((p) => selectedProject === p.id));
	let selectedProjectOrg = $derived(
		(user?.organizations ?? []).find((o) => selectedProjectData?.organization_id === o.id)
	);
	let isLoadingCreatePAT = $state(false);

	let isSelectingProject = $state(false);
	let projectList = $state<HTMLUListElement>();
	let orgElements = $state<HTMLDivElement[]>([]);
	let currentOrg = $state(0);
	let fuse = $derived.by(
		() =>
			new Fuse(user?.projects ?? [], {
				keys: ['name', 'id'],
				threshold: 0.4, // 0.0 = exact match, 1.0 = match all
				includeScore: true
			})
	);
	let searchQuery = $state('');
	let filteredProjects = $derived(
		Object.entries(
			(searchQuery.trim() !== ''
				? fuse.search(searchQuery).map((result) => result.item)
				: (user?.projects ?? [])
			).reduce(
				(acc, project) => {
					if (!acc[project.organization_id]) {
						acc[project.organization_id] = [];
					}

					acc[project.organization_id].push(project);

					return acc;
				},
				{} as Record<string, NonNullable<typeof user>['projects']>
			)
		)
	);

	let observer: IntersectionObserver;
	let observerTimeout: ReturnType<typeof setTimeout>;
	function createObserver() {
		observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						const intersectingOrg = orgElements.findIndex((org) => org === entry.target);
						currentOrg = intersectingOrg;
					}
				});
			},
			{ threshold: [0.5] }
		);

		orgElements.forEach((org) => {
			if (org) observer.observe(org);
		});
	}
</script>

<Dialog.Root bind:open={isCreatingPAT}>
	<Dialog.Content data-testid="create-pat-dialog" class="max-h-[90vh] w-[clamp(0px,30rem,100%)]">
		<Dialog.Header>Create PAT</Dialog.Header>

		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			id="createPat"
			use:enhance={() => {
				isLoadingCreatePAT = true;

				return async ({ result, update }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error('Error creating PAT', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						isCreatingPAT = false;
						selectedExpiry = undefined;
						selectedProject = '';
					}

					isLoadingCreatePAT = false;
					update({ reset: false });
				};
			}}
			method="POST"
			action="?/create-pat"
			class="h-full w-full grow overflow-auto"
		>
			<div class="flex w-full flex-col gap-2 px-4 py-3 text-center sm:px-6">
				<Label required for="pat_name" class="text-xs sm:text-sm">Name</Label>

				<InputText required name="pat_name" placeholder="PAT Name" />
			</div>

			<div class="flex w-full flex-col gap-2 px-4 py-3 text-center sm:px-6">
				<Label for="pat_expiry" class="text-xs sm:text-sm">Expiry</Label>

				<Popover.Root>
					<Popover.Trigger>
						{#snippet child({ props })}
							<Button
								{...props}
								variant="ghost"
								class="h-10 min-w-full justify-start rounded-md border-transparent bg-[#F2F4F7] pl-3 pr-2 text-left font-normal hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e]"
							>
								{selectedExpiry
									? df.format(selectedExpiry.toDate(getLocalTimeZone()))
									: 'No expiry'}
							</Button>
						{/snippet}
					</Popover.Trigger>
					<Popover.Content class="w-auto p-0">
						<Calendar
							bind:value={selectedExpiry}
							type="single"
							minValue={today(getLocalTimeZone()).add({ days: 1 })}
							initialFocus
						/>
					</Popover.Content>
				</Popover.Root>

				<input
					type="text"
					name="pat_expiry"
					hidden
					value={selectedExpiry?.toDate(getLocalTimeZone()).toISOString()}
				/>
			</div>

			<div class="flex w-full flex-col gap-2 px-4 py-3 text-center sm:px-6">
				<Label for="pat_project" class="text-xs sm:text-sm">Project</Label>

				<input type="hidden" bind:value={selectedProject} name="pat_project" />

				<Popover.Root
					bind:open={isSelectingProject}
					onOpenChange={(e) => {
						clearTimeout(observerTimeout);
						if (e) {
							observerTimeout = setTimeout(() => {
								createObserver();
							}, 200);
						} else {
							observer.disconnect();
							currentOrg = 0;
						}
					}}
				>
					<Popover.Trigger>
						{#snippet child({ props })}
							<div class="relative">
								<Button
									{...props}
									title={selectedProject ?? 'Select project'}
									variant="ghost"
									class="h-10 min-w-full justify-start gap-2 rounded-md border-transparent bg-[#F2F4F7] pl-3 pr-2 text-left font-normal hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e] {!selectedProject
										? 'italic text-muted-foreground'
										: ''}"
								>
									{#if selectedProject}
										<div
											class="flex items-center gap-1.5 rounded-lg bg-[#FFB6C333] px-2 py-1 text-[#950048]"
										>
											<PeopleIcon class="mb-0.5 h-[15px] w-[15px]" />
											{selectedProjectOrg?.name ?? selectedProjectData?.organization_id}
										</div>

										{selectedProjectData?.name ?? ''}
									{:else}
										Optional
									{/if}
								</Button>
							</div>
						{/snippet}
					</Popover.Trigger>

					<Popover.Content
						class="grid h-64 w-[var(--bits-popover-anchor-width)] min-w-[var(--bits-popover-anchor-width)] grid-cols-[1fr_2fr] p-0"
					>
						<input
							type="text"
							placeholder="Search projects"
							bind:value={searchQuery}
							oninput={() => {
								if (projectList) projectList.scrollTop = 0;

								currentOrg = 0;
								createObserver();
							}}
							class:hidden={!isSelectingProject}
							class="absolute -top-11 h-10 w-full rounded-md border border-[#E3E3E3] bg-[#F2F4F7] px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus-visible:border-[#d5607c] focus-visible:shadow-[0_0_0_1px_#FFD8DF] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-dark:border-[#42464E] data-dark:bg-[#42464e] data-dark:focus-visible:border-[#5b7ee5]"
						/>

						<div class="flex flex-col gap-1 border-r border-[#E4E7EC] pt-2">
							<p class="mx-3 text-sm uppercase text-[#98A2B3]">Organization</p>

							<ul class="flex h-1 grow flex-col overflow-auto pb-2">
								{#each filteredProjects as [organization, projects], index}
									{@const org = user?.organizations?.find((o) => o.id === organization)}
									<li
										class:bg-[#FFF7F8]={index === currentOrg}
										class:text-[#950048]={index === currentOrg}
										class="mx-1 rounded-lg text-sm transition-colors"
									>
										<button
											onclick={() =>
												orgElements[index].scrollIntoView({
													behavior: 'smooth',
													block: 'start'
												})}
											class="w-full whitespace-normal break-all px-2 py-2 text-left"
										>
											{org?.name ?? organization}
										</button>
									</li>
								{/each}
							</ul>
						</div>

						<div class="flex flex-col gap-1 pt-2">
							<p class="mx-3 text-sm uppercase text-[#98A2B3]">Project</p>

							<ul bind:this={projectList} class="flex h-1 grow flex-col overflow-auto pb-2">
								{#each filteredProjects as [organization, projects], index}
									{@const org = user?.organizations?.find((o) => o.id === organization)}
									<div
										bind:this={orgElements[index]}
										class="mx-1 flex select-none items-center gap-1 rounded-lg bg-[#FFF7F8] py-2 pl-2 pr-1 text-sm text-[#950048]"
									>
										<PeopleIcon class="mb-0.5 h-[15px] w-[15px]" />
										{org?.name ?? organization}
									</div>

									{#each projects as project}
										<li
											class:bg-[#F0F9FF]={project.id === selectedProject}
											class="mx-1 rounded-lg text-sm transition-colors"
										>
											<button
												onclick={() => {
													selectedProject = selectedProject === project.id ? '' : project.id;
													if (selectedProject) {
														isSelectingProject = false;
													}
												}}
												class="relative w-full whitespace-normal break-all py-2 pl-7 pr-2 text-left"
											>
												{#if project.id === selectedProject}
													<span
														class="absolute left-2 top-1/2 flex size-3.5 -translate-y-1/2 items-center justify-center"
													>
														<Check class="size-4" />
													</span>
												{/if}

												{project.name}
											</button>
										</li>
									{/each}
								{/each}
							</ul>
						</div>
					</Popover.Content>
				</Popover.Root>
			</div>
		</form>

		<Dialog.Actions>
			<div class="flex gap-2 overflow-x-auto overflow-y-hidden">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button {...props} variant="link" type="button" class="grow px-6">Cancel</Button>
					{/snippet}
				</Dialog.Close>
				<Button
					type="submit"
					form="createPat"
					loading={isLoadingCreatePAT}
					disabled={isLoadingCreatePAT}
					class="relative grow px-6"
				>
					Create
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
