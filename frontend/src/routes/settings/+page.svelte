<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { session } from '$lib/auth';
	import { t } from '$lib/i18n';

	$effect(() => {
		if ($session !== 'loading' && $session !== null && !$session.is_admin) {
			void goto(resolve('/'));
		}
	});
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
