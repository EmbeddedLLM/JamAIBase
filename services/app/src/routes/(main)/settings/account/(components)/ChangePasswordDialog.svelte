<script lang="ts">
	import { enhance } from '$app/forms';
	import { Eye, EyeOff, KeyRound } from '@lucide/svelte';

	import * as Dialog from '$lib/components/ui/dialog';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { signOut } from '@auth/sveltekit/client';

	let { isChangingPW = $bindable() }: { isChangingPW: boolean } = $props();

	let showPassword = $state(false);
	let loadingChangePW = $state(false);
</script>

<Dialog.Root bind:open={isChangingPW}>
	<Dialog.Content class="h-fit max-h-[90vh] w-[clamp(0px,30rem,100%)]">
		<Dialog.Header>Change password</Dialog.Header>

		<form
			id="changePassword"
			use:enhance={() => {
				loadingChangePW = true;

				return async ({ update, result }) => {
					if (result.type === 'failure') {
						const data = result.data as any;
						toast.error(data.error, {
							id: data?.err_message?.message || JSON.stringify(data),
							description: CustomToastDesc as any,
							componentProps: {
								description: data?.err_message?.message || JSON.stringify(data),
								requestID: data?.err_message?.request_id ?? ''
							}
						});
					}

					loadingChangePW = false;
					isChangingPW = false;
					signOut();
					await update();
				};
			}}
			method="POST"
			action="?/change-password"
			class="grow overflow-auto"
		>
			<div class="flex flex-col gap-3 px-4 py-3 sm:px-6">
				<div class="relative">
					<Input
						type={showPassword ? 'text' : 'password'}
						placeholder="Current password"
						name="password"
						autocomplete="current-password"
						required
						class="pl-10 pr-10"
					/>
					<KeyRound class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
					<button
						type="button"
						onclick={() => (showPassword = !showPassword)}
						class="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
					>
						{#if showPassword}
							<EyeOff class="h-5 w-5" />
						{:else}
							<Eye class="h-5 w-5" />
						{/if}
					</button>
				</div>

				<div class="relative">
					<Input
						type={showPassword ? 'text' : 'password'}
						placeholder="New password"
						name="new_password"
						autocomplete="new-password"
						required
						class="pl-10 pr-10"
					/>
					<KeyRound class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
					<button
						type="button"
						onclick={() => (showPassword = !showPassword)}
						class="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
					>
						{#if showPassword}
							<EyeOff class="h-5 w-5" />
						{:else}
							<Eye class="h-5 w-5" />
						{/if}
					</button>
				</div>

				<div class="relative">
					<Input
						type={showPassword ? 'text' : 'password'}
						placeholder="Confirm new password"
						name="confirmPassword"
						autocomplete="new-password"
						required
						class="pl-10 pr-10"
					/>
					<KeyRound class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
					<button
						type="button"
						onclick={() => (showPassword = !showPassword)}
						class="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
					>
						{#if showPassword}
							<EyeOff class="h-5 w-5" />
						{:else}
							<Eye class="h-5 w-5" />
						{/if}
					</button>
				</div>
			</div>
		</form>

		<Dialog.Actions class="border-t-[1px]">
			<div class="flex justify-end gap-2 pt-3">
				<Button type="button" onclick={() => (isChangingPW = false)} variant="link">Cancel</Button>
				<Button
					form="changePassword"
					type="submit"
					loading={loadingChangePW}
					disabled={loadingChangePW}
				>
					Save changes
				</Button>
			</div>
		</Dialog.Actions>
	</Dialog.Content>
</Dialog.Root>
