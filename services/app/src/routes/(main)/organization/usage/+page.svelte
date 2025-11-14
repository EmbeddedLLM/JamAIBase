<script lang="ts">
	import type { PriceRes } from '$lib/types';

	let { data } = $props();

	let { prices, organizationData } = $derived(data);

	const parseQuotas = (val: number) => (typeof val === 'number' ? +val?.toFixed(6) : '-1');
</script>

<svelte:head>
	<title>Usage - Organization</title>
</svelte:head>

<div class="flex flex-col gap-10 overflow-auto px-4 py-4 sm:px-8 sm:py-6">
	<section data-testid="org-quotas" class="flex flex-col gap-3">
		<h2 class="text-sm font-medium text-[#667085]">QUOTAS</h2>

		<div
			style="grid-auto-rows: 150px;"
			class="grid grid-cols-[repeat(auto-fill,_minmax(240px,_1fr))] gap-2 xs:grid-cols-[repeat(auto-fill,_minmax(285px,_1fr))]"
		>
			{#if organizationData}
				{#each Object.keys(organizationData.quotas) as key}
					{@const productQuota =
						organizationData.price_plan?.products[key as keyof PriceRes['products']]}
					{#if productQuota}
						<div
							data-testid="org-quota-{key.replaceAll('_', '')}"
							class="flex flex-col gap-2 rounded-lg bg-white p-4"
						>
							<span
								title={productQuota.name}
								class="line-clamp-1 flex-[0_0_auto] text-sm font-medium uppercase text-[#98A2B3]"
							>
								{productQuota.name}
							</span>
							<span
								data-testid="quota-used"
								title="{parseQuotas(organizationData.quotas[key].usage)} {productQuota.unit}"
								class="mt-auto line-clamp-1 text-xl font-semibold"
							>
								{parseQuotas(organizationData.quotas[key].usage)}
								{productQuota.unit}
							</span>

							<progress
								value={parseQuotas(organizationData.quotas[key].usage)}
								max={organizationData.quotas[key].quota}
								class="total-progress relative h-[5px] w-full flex-[0_0_auto] appearance-none overflow-hidden !rounded-full"
							></progress>

							<div class="mt-auto grid grid-cols-2 gap-3">
								<span data-testid="quota-balance" class="text-xs text-muted-foreground">
									Balance: <br />
									<span class="font-medium text-[#344054]">
										{parseQuotas(
											organizationData.quotas[key].quota - organizationData.quotas[key].usage
										)}
										{productQuota.unit}
									</span>
								</span>
								<span data-testid="quota-amount" class="text-xs text-muted-foreground">
									Quota: <br />
									<span class="font-medium text-[#344054]">
										{organizationData.quotas[key].quota}
										{productQuota.unit}
									</span>
								</span>
							</div>
						</div>
					{/if}
				{/each}
			{/if}
		</div>
	</section>
</div>
