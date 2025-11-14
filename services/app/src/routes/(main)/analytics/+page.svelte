<script lang="ts">
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';

	import {
		CreditUsageChart,
		EgressUsageChart,
		StorageUsageChart,
		TokenUsageChart
	} from './(charts)';
	import { Skeleton } from '$lib/components/ui/skeleton';

	let { data } = $props();
	let {
		tokenUsage: tokenUsagePromise,
		creditUsage: creditUsagePromise,
		egressUsage: egressUsagePromise,
		storageUsage: storageUsagePromise
	} = $derived(data);

	let tokenLegendContainer: HTMLDivElement | undefined = $state();
	let tokenUsagePromiseResolved = $state(false);
	$effect(() => {
		const p = tokenUsagePromise;

		if (!p || typeof p.then !== 'function') {
			tokenUsagePromiseResolved = Boolean(p);
			return;
		}

		tokenUsagePromiseResolved = false;

		let cancelled = false;

		(async () => {
			try {
				await p;
			} catch {
			} finally {
				if (!cancelled && tokenUsagePromise === p) {
					tokenUsagePromiseResolved = true;
				}
			}
		})();

		return () => {
			cancelled = true;
		};
	});

	let selectedChartEgressStorage: 'egress' | 'storage' = $state('egress');
</script>

<div
	class="relative flex flex-col gap-3 overflow-auto pb-6 pl-6 pr-5 pt-0 [scrollbar-gutter:stable] sm:pl-7 sm:pr-7"
>
	<div
		class="grid grow grid-cols-1 rounded-md border border-[#E5E5E5] bg-white p-2 pt-3 data-dark:border-[#333] data-dark:bg-[#42464E] lg:grid-cols-[1.5fr_minmax(400px,1fr)]"
	>
		<div
			class="border-b border-[#E5E5E5] pb-2 data-dark:border-[#333] lg:border-b-0 lg:border-r lg:pr-2"
		>
			<h3 class="pl-2 font-medium text-[#667085]">Token Usage</h3>

			{#await tokenUsagePromise}
				<div class="flex items-center space-x-4">
					<Skeleton class="h-[24rem] w-full sm:h-[32.3rem]" />
				</div>
			{:then tokenUsage}
				{#if tokenUsage.data}
					<TokenUsageChart usageData={tokenUsage.data} legendContainer={tokenLegendContainer} />
				{:else}
					<div class="flex h-[24rem] items-center justify-center space-x-4 sm:h-[33rem]">
						<p>
							{tokenUsage.error.message || JSON.stringify(tokenUsage.error)}
						</p>
					</div>
				{/if}
			{/await}
		</div>

		<div class="flex flex-col gap-2 pt-2 lg:pt-0">
			<div class="{!tokenUsagePromiseResolved ? 'block' : 'hidden'} flex items-center space-x-4">
				<Skeleton class="h-[26rem] w-full sm:h-[33.8rem] lg:ml-2" />
			</div>
			<div
				bind:this={tokenLegendContainer}
				class="{tokenUsagePromiseResolved
					? 'visible py-1'
					: 'pointer-events-none invisible absolute'} flex grow flex-col gap-2 text-xs sm:text-sm"
			></div>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-3 xl:grid-cols-2">
		<div
			class="flex grow flex-col rounded-md border border-[#E5E5E5] bg-white p-2 pt-3 data-dark:border-[#333] data-dark:bg-[#42464E]"
		>
			<h3 class="pl-2 font-medium text-[#667085]">Credits Spent</h3>

			<div class="h-full w-full border-[#E5E5E5] data-dark:border-[#333]">
				{#await creditUsagePromise}
					<div class="flex items-center space-x-4">
						<Skeleton class="h-[24rem] w-full sm:h-[35rem]" />
					</div>
				{:then creditUsage}
					{#if creditUsage.data}
						<CreditUsageChart usageData={creditUsage.data} />
					{:else}
						<div class="flex h-[24rem] items-center justify-center space-x-4 sm:h-[33rem]">
							<p>
								{creditUsage.error.message || JSON.stringify(creditUsage.error)}
							</p>
						</div>
					{/if}
				{/await}
			</div>
		</div>

		<div
			class="mx-auto flex w-full grow flex-col rounded-md border border-[#E5E5E5] bg-white data-dark:border-[#333] data-dark:bg-[#42464E]"
		>
			<div class="flex justify-center p-3 text-sm sm:text-base">
				<div
					style="grid-template-columns: repeat(2, minmax(5rem, 1fr));"
					class="relative grid w-full place-items-center rounded-[3px] bg-[#E4E7EC] p-0.5 after:pointer-events-none after:absolute after:left-0.5 after:top-1/2 after:z-0 after:h-[calc(100%_-_4px)] after:w-1/2 after:-translate-y-1/2 after:rounded-[3px] after:bg-white after:transition-transform after:duration-200 after:content-[''] data-dark:bg-gray-700 {selectedChartEgressStorage ===
					'egress'
						? 'after:translate-x-0'
						: 'after:translate-x-[calc(100%_-_4px)]'}"
				>
					<button
						onclick={() => (selectedChartEgressStorage = 'egress')}
						class="z-10 w-full rounded-[3px] px-4 py-1 transition-colors ease-in-out {selectedChartEgressStorage ===
						'egress'
							? 'text-[#667085]'
							: 'text-[#98A2B3]'}"
					>
						Egress
					</button>

					<button
						onclick={() => (selectedChartEgressStorage = 'storage')}
						class="z-10 w-full rounded-[3px] px-4 py-1 transition-colors ease-in-out {selectedChartEgressStorage ===
						'storage'
							? 'text-[#667085]'
							: 'text-[#98A2B3]'}"
					>
						Storage
					</button>
				</div>
			</div>

			{#if selectedChartEgressStorage === 'egress'}
				<div class="w-full p-2">
					{#await egressUsagePromise}
						<div class="flex items-center space-x-4">
							<Skeleton class="h-[24rem] w-full sm:h-[33rem]" />
						</div>
					{:then egressUsage}
						{#if egressUsage.data}
							<EgressUsageChart usageData={egressUsage.data} />
						{:else}
							<div class="flex h-[24rem] items-center justify-center space-x-4 sm:h-[33rem]">
								<p>
									{egressUsage.error.message || JSON.stringify(egressUsage.error)}
								</p>
							</div>
						{/if}
					{/await}
				</div>
			{:else}
				<div class="w-full p-2">
					{#await storageUsagePromise}
						<div class="flex items-center space-x-4">
							<Skeleton class="h-[24rem] w-full sm:h-[33rem]" />
						</div>
					{:then storageUsage}
						{#if storageUsage.data}
							<StorageUsageChart usageData={storageUsage.data} />
						{:else}
							<div class="flex h-[24rem] items-center justify-center space-x-4 sm:h-[33rem]">
								<p>
									{storageUsage.error.message || JSON.stringify(storageUsage.error)}
								</p>
							</div>
						{/if}
					{/await}
				</div>
			{/if}
		</div>
	</div>
</div>
