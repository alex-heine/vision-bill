<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { t } from '$lib/i18n';
	import { api } from '$lib/api/client';
	import { queryKeys } from '$lib/query/keys';
	import { queryClient } from '$lib/query/client';
	import CollectionPicker from '$lib/ui/CollectionPicker.svelte';
	import StatisticsCharts from '$lib/ui/StatisticsCharts.svelte';

	let collectionId = $state('');

	const collections = createQuery(
		() => ({ queryKey: queryKeys.collections(), queryFn: () => api.listCollections() }),
		() => queryClient
	);

	const statistics = createQuery(
		() => ({
			queryKey: queryKeys.statistics(12, collectionId),
			queryFn: () => api.getStatistics(12, collectionId || undefined)
		}),
		() => queryClient
	);

	let stats = $derived(statistics.data ?? null);
</script>

<svelte:head>
	<title>{$t('pages.statistics.title')} – {$t('app.name')}</title>
</svelte:head>

<section class="mx-auto max-w-5xl">
	<h1 class="text-2xl font-semibold">{$t('pages.statistics.title')}</h1>
	<p class="mt-1 text-sm text-on-surface-variant">{$t('dashboard.verifiedOnly')}</p>

	<div class="mt-4 max-w-xs">
		<span class="block text-sm text-on-surface-variant">{$t('statistics.collectionFilter')}</span>
		<CollectionPicker
			options={collections.data ?? []}
			mode="single"
			value={collectionId}
			placeholder={$t('statistics.collectionAll')}
			onchange={(v) => (collectionId = v as string)}
		/>
		{#if collections.isSuccess && (collections.data ?? []).length === 0}
			<span class="mt-1 block text-xs text-on-surface-variant"
				>{$t('statistics.collectionEmpty')}</span
			>
		{/if}
	</div>

	{#if statistics.isLoading}
		<p class="mt-6 text-sm text-on-surface-variant">{$t('common.loading')}</p>
	{:else if statistics.error}
		<p
			class="mt-6 rounded-xl border border-outline-variant bg-surface-container-low p-4 text-sm text-on-surface-variant"
		>
			{$t('dashboard.loadError')}
		</p>
	{:else if stats?.verified_receipt_count === 0}
		<div class="mt-6 rounded-xl border border-dashed border-outline-variant p-8 text-center">
			<p class="font-medium">{$t('statistics.emptyTitle')}</p>
			<p class="mt-1 text-sm text-on-surface-variant">{$t('statistics.emptyBody')}</p>
		</div>
	{:else if stats}
		<div class="mt-6">
			<StatisticsCharts {stats} />
		</div>
	{/if}
</section>
