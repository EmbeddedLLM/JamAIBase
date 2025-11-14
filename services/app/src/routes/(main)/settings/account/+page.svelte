<script lang="ts">
	import { enhance } from '$app/forms';
	import { signOut } from '@auth/sveltekit/client';
	import { Trash2 } from '@lucide/svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { DateFormatter, type DateValue } from '@internationalized/date';
	import { getLocale } from '$lib/paraglide/runtime';

	import {
		ChangePasswordDialog,
		CreatePatDialog,
		DeleteAccountDialog,
		DeletePatDialog
	} from './(components)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import InputText from '$lib/components/InputText.svelte';
	import CopyIcon from '$lib/icons/CopyIcon.svelte';

	const df = new DateFormatter(getLocale(), {
		dateStyle: 'long'
	});

	let { data } = $props();
	let { user, pats } = $derived(data);

	let isChangingPW = $state(false);
	let isLoadingChangePassword = $state(false);

	let isCreatingPAT = $state(false);
	let isDeletingPAT: string | null = $state(null);

	let isDeletingAccount = $state(false);
</script>

<svelte:head>
	<title>Account - Settings</title>
</svelte:head>

<section class="flex grow flex-col overflow-auto px-8 py-6">
	<h2 class="mb-3 text-sm font-semibold text-[#667085]">ACCOUNT</h2>

	<div class="mb-1 flex h-min w-[clamp(0px,100%,64rem)] items-center gap-4 rounded-lg bg-white p-4">
		<div
			class="flex aspect-square h-11 w-11 items-center justify-center overflow-hidden rounded-full bg-[#E8F0F3] outline-2"
		>
			{#if user?.picture_url}
				<img src={user.picture_url} alt="User Avatar" class="h-full w-full object-cover" />
			{:else}
				<span class="text-xl uppercase text-[#1B7288]">
					{(user?.name ?? 'Default User').charAt(0)}
				</span>
			{/if}
		</div>

		<div class="flex grow flex-col justify-center">
			<span class="line-clamp-1 text-lg font-medium text-[#0C111D] [word-break:break-word]">
				{user?.name}
			</span>
		</div>
	</div>

	<div class="mb-8 flex h-min w-[clamp(0px,100%,64rem)] flex-col gap-4 rounded-lg bg-white p-4">
		<div class="flex flex-col gap-1">
			<p class="text-xs font-medium uppercase text-[#98A2B3]">User ID</p>
			<span class="text-sm [word-break:break-word]">{user?.id ?? ''}</span>
		</div>

		<div class="flex flex-col gap-1">
			<p class="text-xs font-medium uppercase text-[#98A2B3]">Email</p>
			<span class="text-sm [word-break:break-word]">{user?.email ?? ''}</span>
		</div>
	</div>

	<!-- <Button
		type="button"
		onclick={page.data.auth0Mode ? () => goto('/logout') : signOut}
		class="mb-8 w-fit px-6">Logout</Button
	> -->

	{#if data.auth0Mode}
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<form
			use:enhance={() => {
				isLoadingChangePassword = true;

				return async ({ result, update }) => {
					if (result.type !== 'redirect') {
						//@ts-ignore
						const data = result.data;
						toast.error('Error getting password reset link', {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					}

					isLoadingChangePassword = false;
					update({ reset: false, invalidateAll: false });
				};
			}}
			onkeydown={(event) => event.key === 'Enter' && event.preventDefault()}
			method="POST"
			action="?/change-password"
			class="mb-8 flex w-full flex-col gap-3"
		>
			<h2 class="text-sm font-semibold text-[#667085]">PASSWORD</h2>

			<Button
				type="submit"
				loading={isLoadingChangePassword}
				disabled={isLoadingChangePassword}
				class="w-fit px-6"
			>
				Change Password
			</Button>
		</form>
	{:else}
		<div class="mb-8 flex w-full flex-col gap-3">
			<h2 class="text-sm font-semibold text-[#667085]">PASSWORD</h2>

			<Button type="button" onclick={() => (isChangingPW = true)} class="w-fit px-6">
				Change Password
			</Button>
		</div>
	{/if}

	<div class="flex w-[clamp(0px,100%,64rem)] flex-col">
		<h2 class="mb-3 text-sm font-semibold text-[#667085]">PERSONAL ACCESS TOKEN</h2>

		<div class="flex flex-col gap-1 overflow-auto">
			<div
				role="grid"
				style="grid-template-rows: min-content;"
				class="relative grid h-auto min-h-0 min-w-fit rounded-lg border border-[#F2F4F7] bg-white px-2 data-dark:bg-[#484C55]"
			>
				<div
					role="row"
					style="grid-template-columns: 200px minmax(24rem, 1fr) 240px 170px;"
					class="sticky top-0 z-20 grid h-[50px] bg-white text-sm font-medium data-dark:bg-[#484C55]"
				>
					<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">Name</div>
					<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">Key</div>
					<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">Project</div>
					<div role="columnheader" class="flex items-center px-2 text-[#98A2B3]">Expiry</div>
				</div>
			</div>

			{#if (pats.data ?? []).length > 0}
				<div
					role="grid"
					style="grid-template-rows: repeat({pats.data?.length ?? 0}, min-content);"
					class="relative grid h-auto min-h-0 min-w-fit grow overflow-y-auto overflow-x-visible rounded-lg border border-[#F2F4F7] bg-white px-2 data-dark:bg-[#484C55]"
				>
					{#each pats.data ?? [] as apiKey}
						<div
							role="row"
							style="grid-template-columns: 200px minmax(24rem, 1fr) 240px 170px;"
							class="group/pat relative grid min-h-[50px] text-sm [&>hr]:last:hidden"
						>
							<div role="gridcell" class="flex items-center justify-start gap-1 px-2">
								<p class="w-full break-all py-2">
									{apiKey.name}
								</p>
							</div>

							<div role="gridcell" class="flex items-center px-2">
								<InputText
									obfuscate
									readonly
									name="api_key"
									value={apiKey.id}
									class="w-full border-0 bg-transparent py-0 pl-0.5"
								/>

								<Button
									variant="ghost"
									onclick={() => {
										navigator.clipboard.writeText(apiKey.id);
										toast.success('API key copied to clipboard', { id: 'api-key-copied' });
									}}
									title="Copy API key"
									class="aspect-square h-7 rounded-full p-0 opacity-0 transition-opacity group-hover/pat:opacity-100"
								>
									<CopyIcon class="h-5 text-[#98A2B3]" />
								</Button>

								<Button
									variant="ghost"
									onclick={() => (isDeletingPAT = apiKey.id)}
									title="Delete API key"
									class="aspect-square h-7 rounded-full p-0 opacity-0 transition-opacity group-hover/pat:opacity-100"
								>
									<Trash2 class="h-4 text-[#98A2B3]" />
								</Button>
							</div>

							<div role="gridcell" class="flex items-center justify-start gap-1 px-2">
								<p class="w-full break-all py-2">
									{apiKey.project_id || '-'}
								</p>
							</div>

							<div role="gridcell" class="flex items-center justify-start gap-1 px-2 py-2">
								{apiKey.expiry ? new Date(apiKey.expiry).toLocaleString() : '-'}
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
							<p class="text-sm italic">No PATs have been created for this user</p>
						</div>
					</div>
				</div>
			{/if}
		</div>

		<div class="mb-8 mt-2 flex w-full flex-col gap-3">
			<Button type="button" onclick={() => (isCreatingPAT = true)} class="w-fit px-6">
				Create a Personal Access Token
			</Button>
		</div>
	</div>

	<div class="mt-auto flex flex-col gap-2">
		<h2 class="text-sm font-medium text-[#667085]">ACCOUNT REMOVAL</h2>

		<p class="mb-1 text-[0] text-[#667085] [&>span]:text-[13px]">
			<span>Delete your account permanently.</span>
		</p>

		<div class="flex w-[clamp(0px,100%,600px)] flex-col gap-2 sm:flex-row sm:items-center">
			<Button variant="outline" onclick={() => (isDeletingAccount = true)} class="px-8">
				Delete Account
			</Button>
		</div>
	</div>

	<!-- <div class="relative mt-8 w-full">
		<hr
			class="absolute top-0 left-0 -right-14 border-[#DDD] data-dark:border-[#42464E] -translate-x-8"
		/>
	</div> -->
</section>

<ChangePasswordDialog bind:isChangingPW />
<CreatePatDialog {user} bind:isCreatingPAT />
<DeletePatDialog bind:isDeletingPAT />
<DeleteAccountDialog {user} bind:isDeletingAccount />
