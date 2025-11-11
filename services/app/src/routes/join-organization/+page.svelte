<script lang="ts">
	import { enhance } from '$app/forms';
	import { goto } from '$app/navigation';
	import { activeOrganization, preferredTheme } from '$globalStore';

	import longWhiteLogo from '$lib/assets/Jamai-Long-White-Main.svg';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import * as InputOTP from '$lib/components/ui/input-otp';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import { page } from '$app/state';

	let currentTheme = $derived($preferredTheme == 'DARK' ? 'dark' : 'light');

	let loading = $state(false);
	let code = $state('');

	let errorMessage = $state('');
</script>

<svelte:head>
	<title>Join Organization</title>
</svelte:head>

<div class="flex h-screen flex-col items-center justify-center">
	<img
		src={currentTheme == 'dark' ? longWhiteLogo : longBlackLogo}
		alt=""
		class="absolute top-8 w-40"
	/>

	<div class="w-[clamp(0%,60rem,100%)] rounded-2xl bg-white p-8">
		<div class="text-center">
			<h2 class="text-2xl font-semibold text-[#344054]">Join Organization</h2>
			<p class="mt-3 text-base text-[#667085]">
				Enter the code provided by your organization administrator
			</p>
		</div>

		<form
			id="inviteOrg"
			method="POST"
			use:enhance={() => {
				loading = true;
				return async ({ update, result }) => {
					//@ts-ignore
					const data = result.data;
					errorMessage = data?.err_message?.message || '';
					if (result.type === 'failure') {
						toast.error(data.error, {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					} else if (result.type === 'success') {
						activeOrganization.setOrgCookie(data?.data?.id ?? $activeOrganization?.id);
						await goto('/');
					}
					loading = false;
					await update();
				};
			}}
			class="mt-10 space-y-6"
		>
			<div class="my-14 flex flex-col items-center justify-center gap-2">
				<InputOTP.Root name="code" maxlength={16} bind:value={code}>
					{#snippet children({ cells })}
						<InputOTP.Group class="xl:gap-1">
							{#each cells as cell (cell)}
								<InputOTP.Slot
									{cell}
									class="h-10 w-8 text-base md:h-12 md:w-10 md:text-xl xl:h-16 xl:w-12 xl:rounded-2xl xl:border-l xl:text-2xl xl:first:rounded-l-2xl xl:last:rounded-r-2xl"
								/>
							{/each}
						</InputOTP.Group>
					{/snippet}
				</InputOTP.Root>

				{#if errorMessage}
					<Alert variant="destructive" class="w-max animate-in fade-in">
						<AlertDescription>{errorMessage}</AlertDescription>
					</Alert>
				{/if}
			</div>
		</form>

		<div class="text-center text-sm text-[#667085]">
			<p>Don't have a code? Contact your organization administrator for Invitation.</p>
		</div>

		<div class="mx-auto mt-8 flex w-full flex-col gap-4 md:w-1/2">
			<Button
				{loading}
				disabled={loading || code.length < 16}
				onclick={() => {
					page.url.searchParams.append('token', code);
					goto(`?${page.url.searchParams}`);
				}}
			>
				Join organization
			</Button>
			<Button href="/new-organization" variant="link" class="text-sm">
				Or create a new organization
			</Button>
		</div>
	</div>
</div>
