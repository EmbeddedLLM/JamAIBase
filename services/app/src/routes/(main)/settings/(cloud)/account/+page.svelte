<script lang="ts">
	import { enhance } from '$app/forms';

	import { Button } from '$lib/components/ui/button';
	import UserRole from '$lib/components/UserRole.svelte';
	import LogoutIcon from '$lib/icons/LogoutIcon.svelte';

	export let data;
	$: ({ user } = data);

	let isLoadingChangePassword = false;
</script>

<svelte:head>
	<title>Account - Settings</title>
</svelte:head>

<div class="flex flex-col px-8 py-6 overflow-auto">
	<section class="flex flex-col gap-3 w-full xl:w-2/3">
		<h2 class="font-semibold text-[#667085] text-sm">ACCOUNT</h2>

		<div class="relative grow flex flex-col gap-4 h-full">
			<div class="flex items-center">
				<div class="flex items-center gap-4 pt-4 pb-2">
					<div class="relative placeholder pointer-events-none select-none rounded-full">
						<div
							class="flex items-center justify-center bg-[#93D48D] rounded-full h-[5.8rem] w-[5.8rem] outline-2 aspect-square overflow-hidden"
						>
							<img src={user?.picture} alt="User Avatar" class="object-cover w-full h-full" />
						</div>
					</div>

					<div class={`grow flex flex-col justify-center gap-1`}>
						<span class="text-xl break-all line-clamp-1 font-medium">{user?.nickname}</span>
						<UserRole class="font-medium" />
					</div>
				</div>
			</div>

			<div
				class="flex flex-col w-full min-w-fit border border-[#E3E3E3] data-dark:border-[#42464E] rounded-[0.875rem] data-dark:bg-[#484C55]"
			>
				<div
					class="grid grid-cols-[10rem_auto] gap-2 text-start text-sm px-4 py-3 border-b border-[#E3E3E3] data-dark:border-[#42464E]"
				>
					<span class="text-[#999] font-medium">User ID</span>

					<span class="text-[#666666] data-dark:text-white font-medium bg-transparent resize-none">
						{user?.sub}
					</span>
				</div>

				<div
					class="grid grid-cols-[10rem_auto] gap-2 text-start text-sm px-4 py-3 border-[#E3E3E3] data-dark:border-[#42464E]"
				>
					<span class="text-[#999] font-medium">Email</span>

					<span class="text-[#666666] data-dark:text-white font-medium bg-transparent">
						{user?.email}
					</span>
				</div>
			</div>
		</div>
	</section>

	<div class="relative mt-8 w-full">
		<hr
			class="absolute top-0 left-0 -right-14 border-[#DDD] data-dark:border-[#42464E] -translate-x-8"
		/>
	</div>

	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<form
		use:enhance={() => {
			isLoadingChangePassword = true;

			return async ({ result, update }) => {
				if (result.type !== 'redirect') {
					// @ts-ignore
					alert('Error getting password change URL: ' + JSON.stringify(result.data));
				}

				isLoadingChangePassword = false;
				update({ reset: false, invalidateAll: false });
			};
		}}
		on:keydown={(event) => event.key === 'Enter' && event.preventDefault()}
		method="POST"
		action="?/change-password"
		class="flex flex-col gap-3 pt-6 w-full"
	>
		<h2 class="font-semibold text-[#667085] text-sm">PASSWORD</h2>

		<Button
			type="submit"
			loading={isLoadingChangePassword}
			disabled={isLoadingChangePassword}
			variant="secondary"
			class="w-fit px-6 rounded-full"
		>
			Change Password
		</Button>
	</form>

	<div class="relative mt-8 w-full">
		<hr
			class="absolute top-0 left-0 -right-14 border-[#DDD] data-dark:border-[#42464E] -translate-x-8"
		/>
	</div>
</div>
