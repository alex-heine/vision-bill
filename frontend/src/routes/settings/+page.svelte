<script lang="ts">
	import { t } from '$lib/i18n';
</script>

<svelte:head>
	<title>{$t('pages.settings.title')} – {$t('app.name')}</title>
</svelte:head>

<section>
	<h1 class="text-2xl font-semibold">{$t('pages.settings.title')}</h1>
	<p class="mt-2 text-on-surface-variant">
		{$t('pages.settings.placeholder')}
	</p>
</section>
