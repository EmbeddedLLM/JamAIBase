<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { tick } from 'svelte';
	import { signOut } from '@auth/sveltekit/client';
	import { goto } from '$app/navigation';
	import { activeOrganization } from '$globalStore';
	import { currencies } from '$lib/constants';
	import logger from '$lib/logger';
	import type { OrganizationReadRes } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import InputText from '$lib/components/InputText.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Select from '$lib/components/ui/select';

	const { PUBLIC_JAMAI_URL } = env;

	let { data } = $props();
	let { user } = $derived(data);

	let selectedCurrency = $state<keyof typeof currencies>('USD');
	let isLoading = $state(false);

	async function handleSubmitForm(e: SubmitEvent & { currentTarget: HTMLFormElement }) {
		e.preventDefault();
		if (isLoading) return;

		isLoading = true;

		const formData = new FormData(e.currentTarget);
		const organization_name = formData.get('organization_name') as string;

		//* Create organization
		const createOrgRes = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/organizations`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				name: organization_name
				// currency: selectedCurrency
			})
		});
		const createOrgBody = await createOrgRes.json();

		if (!createOrgRes.ok) {
			logger.error('NEWORG_CREATEORG_FAILED', createOrgBody);
			toast.error('Failed to create organization', {
				id: createOrgBody.message || JSON.stringify(createOrgBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: createOrgBody.message || JSON.stringify(createOrgBody),
					requestID: createOrgBody.request_id ?? ''
				}
			});
			isLoading = false;
			return;
		}

		activeOrganization.setOrgCookie((createOrgBody as OrganizationReadRes).id);

		await tick();

		// TODO: client nav might be causing overlay here to persist, hard load for temp fix
		if (createOrgBody.active) {
			window.location.href = '/';
		} else {
			window.location.href = '/organization/billing?upgrade=free';
		}
	}
</script>

<svelte:head>
	<title>Create new organization</title>
</svelte:head>

<main class="flex h-screen flex-col overflow-auto px-8">
	<Dialog.Root open={true}>
		<Dialog.Content
			interactOutsideBehavior="ignore"
			escapeKeydownBehavior="ignore"
			overlayClass="bg-transparent backdrop-blur-none"
			class="max-h-[90vh] w-[clamp(0px,35rem,100%)]"
		>
			<div
				class="relative flex h-min items-center justify-between space-y-1.5 px-6 pb-2 pt-8 text-2xl font-bold text-[#666666] data-dark:text-white sm:text-left"
			>
				{#if (user?.org_memberships ?? []).length > 0}
					Create a new organization
				{:else}
					Welcome, <br /> let's get you ready!
				{/if}
			</div>

			<div class="flex grow flex-col gap-4 overflow-auto pb-2">
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<form
					id="createOrg"
					onsubmit={handleSubmitForm}
					class="flex w-full flex-col gap-3 px-8 pt-2"
				>
					<div class="flex flex-col gap-1">
						<Label
							required
							for="organization_name"
							class="text-left text-sm font-medium text-black"
						>
							Organization name
						</Label>

						<InputText required placeholder="Personal" name="organization_name" />

						<span class="w-fit text-xs italic text-muted-foreground [word-break:break-word]">
							Your organization's display name. You can change this later.
						</span>
					</div>

					<!-- <div class="flex flex-col gap-1">
						<Label required for="currency" class="text-left text-sm font-medium text-black">
							Currency
						</Label>

						<Select.Root required name="currency" type="single" bind:value={selectedCurrency}>
							<Select.Trigger
								class="h-10 min-w-full border-transparent bg-[#F2F4F7] pl-3 pr-2 hover:bg-[#e1e2e6] disabled:opacity-100 data-dark:bg-[#42464e]"
							>
								{currencies[selectedCurrency]
									? `${selectedCurrency} - ${currencies[selectedCurrency]}`
									: 'Select a currency'}
							</Select.Trigger>
							<Select.Content>
								{#each Object.entries(currencies) as [code, name]}
									<Select.Item value={code} label={name}>
										{code} - {name}
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div> -->
				</form>

				<div class="px-6">
					<Button data-sveltekit-reload href="/join-organization" variant="link" class="text-sm">
						Or join an existing organization
					</Button>
				</div>
			</div>

			<Dialog.Actions>
				<div class="flex w-full justify-between overflow-x-auto overflow-y-hidden">
					{#if (user?.org_memberships ?? []).length > 0}
						<Button data-sveltekit-reload variant="link" href="/">Cancel</Button>
					{:else}
						<Button
							onclick={data.auth0Mode ? () => goto('/logout') : signOut}
							variant="destructive"
						>
							<span>Log Out</span>
						</Button>
					{/if}

					<Button
						data-testid="create-organization-btn"
						type="submit"
						form="createOrg"
						loading={isLoading}
						disabled={isLoading}
						class="relative px-6"
					>
						{#if (user?.org_memberships ?? []).length > 0}
							Create
						{:else}
							Get Started
						{/if}
					</Button>
				</div>
			</Dialog.Actions>
		</Dialog.Content>
	</Dialog.Root>
</main>

<style>
	main {
		background-image: url('$lib/assets/jamai-onboarding-bg.svg');
		background-color: white;
		background-size: cover;
	}
</style>
