<script lang="ts">
	import type { Snippet } from 'svelte';
	import { QueryClientProvider, createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import '../app.css';
	import { api } from '$lib/api/client';
	import { LOCALES, locale, setLocale, t } from '$lib/i18n';
	import { queryClient } from '$lib/query/client';
	import { queryKeys } from '$lib/query/keys';
	import Snackbar from '$lib/ui/Snackbar.svelte';
	import Icon, { type IconName } from '$lib/ui/Icon.svelte';

	let { children }: { children: Snippet } = $props();

	let theme = $state<'light' | 'dark'>(
		document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
	);

	function toggleTheme() {
		theme = theme === 'light' ? 'dark' : 'light';
		document.documentElement.dataset.theme = theme;
		localStorage.setItem('vb-theme', theme);
	}

	function onLocaleChange(event: Event) {
		const select = event.currentTarget as HTMLSelectElement;
		const value = select.value;
		if (value === 'en' || value === 'de') {
			void setLocale(value);
		}
	}

	const queue = createQuery(
		() => ({
			queryKey: queryKeys.images({ status: ['pending', 'failed'] }),
			queryFn: () => api.listImages({ status: ['pending', 'failed'] }),
			staleTime: 30_000,
			refetchInterval: 30_000
		}),
		() => queryClient
	);

	let queueCount = $derived(queue.data?.length ?? 0);
	let activePath = $derived(page.url.pathname);

	type NavPath =
		'/' | '/statistics' | '/queue' | '/upload' | '/receipts' | '/benchmarks/results' | '/settings';

	let navItems = $derived([
		{ path: '/', label: $t('nav.dashboard'), icon: 'dashboard' as const },
		{ path: '/statistics', label: $t('nav.statistics'), icon: 'dashboard' as const },
		{ path: '/queue', label: $t('nav.queue'), icon: 'queue' as const },
		{ path: '/upload', label: $t('nav.upload'), icon: 'upload' as const },
		{ path: '/receipts', label: $t('nav.receipts'), icon: 'receipts' as const },
		{ path: '/benchmarks/results', label: $t('nav.benchmarks'), icon: 'dashboard' as const },
		{ path: '/settings', label: $t('nav.settings'), icon: 'settings' as const }
	] satisfies { path: NavPath; label: string; icon: IconName }[]);

	function isActive(path: string) {
		return path === '/' ? activePath === '/' : activePath.startsWith(path);
	}
</script>

<QueryClientProvider client={queryClient}>
	<header
		class="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-outline-variant bg-surface-container px-4 md:px-8"
	>
		<a href={resolve('/')} class="flex items-center gap-2 text-lg font-semibold text-primary">
			<Icon icon="receipts" />
			<span>{$t('app.name')}</span>
		</a>
		<div class="flex items-center gap-2">
			{#if queueCount > 0}
				<a
					href={resolve('/queue')}
					title={$t('nav.queue')}
					class="flex items-center gap-1 rounded-full bg-tertiary-container px-3 py-1 text-sm font-medium text-on-tertiary-container"
				>
					<Icon icon="queue" />
					{queueCount}
				</a>
			{/if}
			<label class="sr-only" for="locale-select">{$t('language.label')}</label>
			<select
				id="locale-select"
				class="rounded-lg border border-outline-variant bg-surface px-2 py-1 text-sm"
				value={$locale}
				onchange={onLocaleChange}
			>
				{#each LOCALES as code (code)}
					<option value={code}>{code.toUpperCase()}</option>
				{/each}
			</select>
			<button
				type="button"
				class="rounded-lg p-2 hover:bg-surface-container-high"
				title={$t('theme.toggle')}
				aria-label={$t('theme.toggle')}
				onclick={toggleTheme}
			>
				<Icon icon={theme === 'dark' ? 'theme-light' : 'theme-dark'} />
			</button>
		</div>
	</header>

	<div class="flex">
		<nav
			class="sticky top-16 hidden h-[calc(100vh-4rem)] w-56 shrink-0 flex-col gap-1 overflow-y-auto border-r border-outline-variant bg-surface-container-low p-4 md:flex"
			aria-label="Main"
		>
			{#each navItems as item (item.path)}
				<a
					href={resolve(item.path)}
					aria-current={isActive(item.path) ? 'page' : undefined}
					class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium {isActive(
						item.path
					)
						? 'bg-primary-container text-on-primary-container'
						: 'text-on-surface-variant hover:bg-surface-container-high'}"
				>
					<Icon icon={item.icon} />
					{item.label}
				</a>
			{/each}
		</nav>

		<main class="min-h-[calc(100vh-4rem)] flex-1 p-4 pb-24 md:p-8 md:pb-8">
			{@render children()}
		</main>
	</div>

	<nav
		class="fixed inset-x-0 bottom-0 z-20 flex border-t border-outline-variant bg-surface-container md:hidden"
		aria-label="Main"
	>
		{#each navItems as item (item.path)}
			{#if item.path === '/upload'}
				<div class="relative flex flex-1 justify-center">
					<a
						href={resolve('/upload')}
						aria-label={$t('nav.upload')}
						aria-current={isActive(item.path) ? 'page' : undefined}
						class="absolute -top-5 flex size-14 items-center justify-center rounded-full bg-primary text-on-primary shadow-elevation-3"
					>
						<Icon icon="upload" />
					</a>
				</div>
			{:else}
				<a
					href={resolve(item.path)}
					aria-current={isActive(item.path) ? 'page' : undefined}
					class="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs {isActive(item.path)
						? 'text-primary'
						: 'text-on-surface-variant'}"
				>
					<Icon icon={item.icon} />
					{item.label}
				</a>
			{/if}
		{/each}
	</nav>

	<Snackbar />
</QueryClientProvider>
