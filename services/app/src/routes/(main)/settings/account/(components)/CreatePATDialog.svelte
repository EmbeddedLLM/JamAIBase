<script lang="ts">
	import { enhance } from '$app/forms';
	import { DateFormatter, getLocalTimeZone, today, type DateValue } from '@internationalized/date';
	import { getLocale } from '$lib/paraglide/runtime';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Calendar } from '$lib/components/ui/calendar';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Popover from '$lib/components/ui/popover';
	import * as Select from '$lib/components/ui/select';
	import InputText from '$lib/components/InputText.svelte';
	import type { PageData } from '../$types';

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

				<Select.Root type="single" allowDeselect bind:value={selectedProject} name="pat_project">
					<Select.Trigger
						title={selectedProject ?? 'Select project'}
						class="border-transparent bg-[#F2F4F7] hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e]"
					>
						<div>
							{#if selectedProject}
								{selectedProjectData?.name ?? ''}&nbsp;&nbsp;–&nbsp;
								<span class="italic">
									{selectedProjectOrg?.name ?? selectedProjectData?.organization_id}
								</span>
							{:else}
								Optional
							{/if}
						</div>
					</Select.Trigger>
					<Select.Content>
						{#each user?.projects ?? [] as project}
							{@const projectOrg = (user?.organizations ?? []).find(
								(o) => project.organization_id === o.id
							)}
							<Select.Item
								title={project.id}
								value={project.id}
								label={`${project.name} (${projectOrg?.name ?? project.organization_id})`}
							>
								{project.name}&nbsp;&nbsp;–&nbsp;
								<span class="italic">
									{projectOrg?.name ?? project.organization_id}
								</span>
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
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
