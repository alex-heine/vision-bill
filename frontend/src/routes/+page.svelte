<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { resolve } from '$app/paths';
	import { t } from '$lib/i18n';
	import { fetchAllReceipts } from '$lib/api/receipts';
	import {
		currentMonthReceipts,
		totalsByCategory,
		totalsByCurrency,
		verifiedReceipts
	} from '$lib/receipt-stats';
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
	let monthTotals = $derived(totalsByCurrency(currentMonthReceipts(verified)));
	let categoryTotals = $derived(totalsByCategory(verified).slice(0, 4));
</script>

<svelte:head>
	<title>{$t('pages.dashboard.title')} – {$t('app.name')}</title>
</svelte:head>

<section class="mx-auto max-w-5xl">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold">{$t('pages.dashboard.title')}</h1>
			<p class="mt-1 text-sm text-on-surface-variant">{$t('dashboard.verifiedOnly')}</p>
		</div>
		<a
			href={resolve('/statistics')}
			class="rounded-lg px-4 py-2 text-sm font-medium text-primary hover:bg-primary-container"
		>
			{$t('dashboard.openStatistics')}
		</a>
	</div>

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
			<p class="font-medium">{$t('dashboard.emptyTitle')}</p>
			<p class="mt-1 text-sm text-on-surface-variant">{$t('dashboard.emptyBody')}</p>
		</div>
	{:else}
		<div class="mt-6 grid gap-4 sm:grid-cols-2">
			<div class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
				<p class="text-sm text-on-surface-variant">{$t('dashboard.verifiedReceipts')}</p>
				<p class="mt-2 text-3xl font-semibold">{verified.length}</p>
			</div>
			<div class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
				<p class="text-sm text-on-surface-variant">{$t('dashboard.thisMonth')}</p>
				{#if monthTotals.length > 0}
					{#each monthTotals as total (total.currency)}
						<p class="mt-2 text-2xl font-semibold">{formatMoney(total.total, total.currency)}</p>
					{/each}
				{:else}
					<p class="mt-2 text-2xl font-semibold">—</p>
				{/if}
			</div>
		</div>

		<div class="mt-6 rounded-xl border border-outline-variant bg-surface-container-low p-5">
			<h2 class="font-semibold">{$t('dashboard.topCategories')}</h2>
			<ul class="mt-4 grid gap-3 sm:grid-cols-2">
				{#each categoryTotals as item (`${item.category}-${item.currency}`)}
					<li class="flex items-center justify-between gap-3 rounded-lg bg-surface-container p-3">
						<span class="text-sm">{$t(`categories.${item.category}`)}</span>
						<span class="text-sm font-medium">{formatMoney(item.total, item.currency)}</span>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</section>
