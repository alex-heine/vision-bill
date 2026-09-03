<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { t } from '$lib/i18n';
	import { fetchAllReceipts } from '$lib/api/receipts';
	import { totalsByCategory, totalsByCurrency, verifiedReceipts } from '$lib/receipt-stats';
	import { queryKeys } from '$lib/query/keys';
	import { queryClient } from '$lib/query/client';
	import { formatMoney } from '$lib/ui/money';

	const receipts = createQuery(
		() => ({
			queryKey: queryKeys.receipts({ status: ['verified'] }),
			queryFn: () => fetchAllReceipts({ status: ['verified'] })
		}),
		() => queryClient
	);

	let verified = $derived(verifiedReceipts(receipts.data ?? []));
	let currencyTotals = $derived(totalsByCurrency(verified));
	let categoryTotals = $derived(totalsByCategory(verified));
	let largestCategoryTotal = $derived(Math.max(...categoryTotals.map((item) => item.total), 1));
</script>

<svelte:head>
	<title>{$t('pages.statistics.title')} – {$t('app.name')}</title>
</svelte:head>

<section class="mx-auto max-w-5xl">
	<h1 class="text-2xl font-semibold">{$t('pages.statistics.title')}</h1>
	<p class="mt-1 text-sm text-on-surface-variant">{$t('dashboard.verifiedOnly')}</p>

	{#if receipts.isLoading}
		<p class="mt-6 text-sm text-on-surface-variant">{$t('common.loading')}</p>
	{:else if receipts.error}
		<p
			class="mt-6 rounded-xl border border-outline-variant bg-surface-container-low p-4 text-sm text-on-surface-variant"
		>
			{$t('dashboard.loadError')}
		</p>
	{:else if verified.length === 0}
		<div class="mt-6 rounded-xl border border-dashed border-outline-variant p-8 text-center">
			<p class="font-medium">{$t('statistics.emptyTitle')}</p>
			<p class="mt-1 text-sm text-on-surface-variant">{$t('statistics.emptyBody')}</p>
		</div>
	{:else}
		<div class="mt-6 grid gap-4 sm:grid-cols-2">
			<div class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
				<p class="text-sm text-on-surface-variant">{$t('statistics.receiptCount')}</p>
				<p class="mt-2 text-3xl font-semibold">{verified.length}</p>
			</div>
			<div class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
				<p class="text-sm text-on-surface-variant">{$t('statistics.totalSpend')}</p>
				{#each currencyTotals as total (total.currency)}
					<p class="mt-2 text-2xl font-semibold">{formatMoney(total.total, total.currency)}</p>
				{/each}
			</div>
		</div>

		<div class="mt-6 rounded-xl border border-outline-variant bg-surface-container-low p-5">
			<h2 class="font-semibold">{$t('statistics.byCategory')}</h2>
			<ul class="mt-4 space-y-4">
				{#each categoryTotals as item (`${item.category}-${item.currency}`)}
					<li>
						<div class="mb-1 flex justify-between gap-3 text-sm">
							<span>{$t(`categories.${item.category}`)} · {item.count}</span>
							<span class="font-medium">{formatMoney(item.total, item.currency)}</span>
						</div>
						<div class="h-2 overflow-hidden rounded-full bg-surface-container-highest">
							<div
								class="h-full rounded-full bg-primary"
								style={`width: ${(item.total / largestCategoryTotal) * 100}%`}
							></div>
						</div>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</section>
