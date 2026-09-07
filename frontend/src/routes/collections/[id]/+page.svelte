<script lang="ts">
	import { resolve } from '$app/paths';
	import { t } from '$lib/i18n';
	// Minimal placeholder so the overview card's link + resolve() type-check.
	// Task 11 replaces this with the full collection detail page.
</script>

<svelte:head>
	<title>{$t('collections.title')} – {$t('app.name')}</title>
</svelte:head>

<section class="mx-auto max-w-3xl">
	<h1 class="text-2xl font-semibold">{$t('collections.title')}</h1>
	<a href={resolve('/collections')} class="mt-4 inline-block text-sm font-medium text-primary">
		← {$t('common.back')}
	</a>
</section>
