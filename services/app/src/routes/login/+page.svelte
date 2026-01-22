<script lang="ts">
	import { page } from '$app/state';
	import { signIn } from '@auth/sveltekit/client';
	import longBlackLogo from '$lib/assets/Jamai-Long-Black-Main.svg';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import logger from '$lib/logger';
	import { CircleUser, Eye, EyeOff, KeyRound } from 'lucide-svelte';
	import { getAuthErrorMessage } from './auth-errors';

	let email = $state('');
	let password = $state('');
	let showPassword = $state(false);
	let error = $state('');

	let isLoading = $state(false);

	// Handle URL error parameters
	const searchParams = page.url.searchParams;
	const hasError = searchParams.has('error');
	const errorCode = searchParams.get('code');

	if (hasError && errorCode) {
		error = getAuthErrorMessage(errorCode);
	} else {
		error = '';
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		isLoading = true;
		error = '';

		if (!email) {
			error = 'All fields are required';
			isLoading = false;
			return;
		}

		try {
			await signIn('credentials', {
				email,
				password,
				isNewAccount: false,
				callbackUrl: location.origin,
				redirectTo: page.url.searchParams.get('returnTo') ?? undefined
			});
		} catch (err) {
			logger.error('error', err);
			if (err instanceof Error) {
				error = err.message;
			}
		} finally {
			isLoading = false;
		}
	}
</script>

<svelte:head>
	<title>Log in | JamAI Base</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center">
	<div class="mx-4 w-full max-w-md rounded-lg border border-gray-100 bg-white p-8 shadow-lg">
		<div class="mb-8 space-y-4 text-center">
			<img src={longBlackLogo} alt="" class="mx-auto w-2/3" />
			<p class="mt-2 text-gray-600">Welcome back</p>
		</div>

		<form onsubmit={handleSubmit} class="space-y-5">
			<div class="space-y-4">
				<div class="relative">
					<Input
						type="text"
						bind:value={email}
						autocomplete="email"
						placeholder="Email"
						required
						class="pl-10"
					/>
					<CircleUser class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
				</div>

				<div class="relative">
					<Input
						type={showPassword ? 'text' : 'password'}
						bind:value={password}
						autocomplete="current-password"
						placeholder="Password"
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

			{#if error}
				<Alert variant="destructive">
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}

			<Button
				type="submit"
				disabled={isLoading}
				loading={isLoading}
				variant="default"
				class="w-full"
			>
				Login
			</Button>
		</form>

		<div class="mt-6 flex flex-col items-center gap-3">
			<span>Don't have an account?</span>
			<Button
				href="/register{page.url.searchParams.size > 0 ? `?${page.url.searchParams}` : ''}"
				disabled={isLoading}
				variant="outline"
				class="w-full"
			>
				Sign Up
			</Button>
		</div>
	</div>
</div>
