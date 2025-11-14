<script lang="ts">
	import { signOut } from '@auth/sveltekit/client';
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import type { User } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';

	let { data } = $props();
	let { user } = $derived(data);

	let isLoading = $state(false);
	let emailResent = $state(false);
</script>

<svelte:head>
	<title>Verify your email</title>
</svelte:head>

<main class="flex h-screen flex-col overflow-auto px-8">
	<div class="flex flex-1 flex-col items-center justify-center">
		<div class="mb-6 flex flex-col items-center justify-center gap-1">
			<div
				class="flex aspect-square h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-[#E8F0F3] outline-2"
			>
				{#if user?.picture_url}
					<img src={user.picture_url} alt="User Avatar" class="h-full w-full object-cover" />
				{:else}
					<span class="text-4xl uppercase text-[#1B7288]">
						{((page.data.user as User).name ?? 'Default User').charAt(0)}
					</span>
				{/if}
			</div>
			<span class="text-center font-semibold">{user?.email}</span>
		</div>

		<h1 class="text-3xl font-bold">Verify your email</h1>
		<p class="mt-4 text-center">
			We've sent you an email with a link to verify your email address. Please check your inbox and
			click the link to continue.
		</p>

		<div class="mt-8 flex items-center gap-2">
			<form
				use:enhance={({ cancel }) => {
					if (emailResent) {
						cancel();
					} else {
						isLoading = true;
					}

					return async ({ result, update }) => {
						if (result.type !== 'success') {
							toast.error('Error resending verification email', {
								//@ts-ignore
								id: result.data?.err_message?.message || JSON.stringify(result.data),
								description: CustomToastDesc as any,
								componentProps: {
									//@ts-ignore
									description: result.data?.err_message?.message || JSON.stringify(result.data)
								}
							});
						} else {
							emailResent = true;
						}

						isLoading = false;
						update({ reset: result.type === 'success', invalidateAll: false });
					};
				}}
				method="POST"
				action="?/resend-verification-email"
			>
				<Button type="submit" loading={isLoading} disabled={isLoading || emailResent}>
					Resend verification email
				</Button>
			</form>

			<Button type="button" variant="destructive" onclick={signOut}>
				<span>Log Out</span>
			</Button>
		</div>

		<p class="mt-2 text-center text-sm {emailResent ? 'visible' : 'invisible'}">
			Verification email sent, please check your inbox.
		</p>
	</div>
</main>
