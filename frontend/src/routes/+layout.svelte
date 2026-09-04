<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onMount } from 'svelte';
	import { QueryClientProvider, createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import '../app.css';
	import { api } from '$lib/api/client';
	import { initSession, session, signOut } from '$lib/auth';
	import { LOCALES, locale, setLocale, t } from '$lib/i18n';
	import { queryClient } from '$lib/query/client';
	import { queryKeys } from '$lib/query/keys';
	import Snackbar from '$lib/ui/Snackbar.svelte';
	import Icon, { type IconName } from '$lib/ui/Icon.svelte';

	let { children }: { children: Snippet } = $props();

	let theme = $state<'light' | 'dark'>(
		document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
	);
	let moreOpen = $state(false);
	let moreMenu: HTMLDivElement | undefined = $state();
	let moreButton: HTMLButtonElement | undefined = $state();

	function toggleTheme() {
		theme = theme === 'light' ? 'dark' : 'light';
		document.documentElement.dataset.theme = theme;
		localStorage.setItem('vb-theme', theme);
		moreOpen = false;
	}

	function closeMore(event?: MouseEvent | KeyboardEvent) {
		if (event instanceof KeyboardEvent && event.key !== 'Escape') return;
		moreOpen = false;
		if (event instanceof KeyboardEvent) moreButton?.focus();
	}

	function onLocaleChange(event: Event) {
		const select = event.currentTarget as HTMLSelectElement;
		const value = select.value;
		if (value === 'en' || value === 'de') {
			void setLocale(value);
			moreOpen = false;
		}
	}

	async function handleSignOut() {
		await signOut();
		void goto(resolve('/login'));
	}

	// Resolved user for rendering; null while loading or signed out.
	let currentUser = $derived.by(() => {
		const s = $session;
		return s === 'loading' || s === null ? null : s;
	});

	let activePath = $derived(page.url.pathname);

	// Populate the session once on start (the HttpOnly cookie is the source of
	// truth; this is just the client's view of it).
	onMount(() => {
		void initSession();
		const onDocumentClick = (event: MouseEvent) => {
			if (
				moreOpen &&
				moreMenu &&
				moreButton &&
				!moreMenu.contains(event.target as Node) &&
				!moreButton.contains(event.target as Node)
			)
				moreOpen = false;
		};
		document.addEventListener('click', onDocumentClick);
		document.addEventListener('keydown', closeMore);
		return () => {
			document.removeEventListener('click', onDocumentClick);
			document.removeEventListener('keydown', closeMore);
		};
	});

	// Auth guard: signed out -> the login page; signed in on /login -> home.
	$effect(() => {
		if ($session === null && activePath !== '/login') void goto(resolve('/login'));
		if (currentUser !== null && activePath === '/login') void goto(resolve('/'));
	});

	const queue = createQuery(
		() => ({
			queryKey: queryKeys.images({ status: ['pending', 'failed'] }),
			queryFn: () => api.listImages({ status: ['pending', 'failed'] }),
			staleTime: 30_000,
			refetchInterval: 30_000,
			enabled: currentUser !== null
		}),
		() => queryClient
	);

	let queueCount = $derived(queue.data?.length ?? 0);

	type NavPath =
		| '/'
		| '/search'
		| '/statistics'
		| '/queue'
		| '/upload'
		| '/receipts'
		| '/benchmarks/results'
		| '/settings';
	type MobileNavPath = '/search' | '/upload' | '/receipts';

	let navItems = $derived([
		{ path: '/search', label: $t('nav.search'), icon: 'search' as const },
		{ path: '/', label: $t('nav.dashboard'), icon: 'dashboard' as const },
		{ path: '/statistics', label: $t('nav.statistics'), icon: 'dashboard' as const },
		{ path: '/queue', label: $t('nav.queue'), icon: 'queue' as const },
		{ path: '/upload', label: $t('nav.upload'), icon: 'upload' as const },
		{ path: '/receipts', label: $t('nav.receipts'), icon: 'receipts' as const },
		...(currentUser?.is_admin
			? [
					{
						path: '/benchmarks/results' as const,
						label: $t('nav.benchmarks'),
						icon: 'dashboard' as const
					},
					{ path: '/settings' as const, label: $t('nav.settings'), icon: 'settings' as const }
				]
			: [])
	] satisfies { path: NavPath; label: string; icon: IconName }[]);

	let mobileNavItems = $derived([
		{ path: '/search', label: $t('nav.search'), icon: 'search' as const },
		{ path: '/upload', label: $t('nav.upload'), icon: 'upload' as const },
		{ path: '/receipts', label: $t('nav.receipts'), icon: 'receipts' as const }
	] satisfies { path: MobileNavPath; label: string; icon: IconName }[]);

	function isActive(path: string) {
		return path === '/' ? activePath === '/' : activePath.startsWith(path);
	}
</script>

<QueryClientProvider client={queryClient}>
	{#if $session === 'loading'}
		<div class="flex min-h-[calc(100vh-4rem)] items-center justify-center p-8">
			<p class="text-sm text-on-surface-variant">{$t('common.loading')}</p>
		</div>
	{:else if currentUser === null}
		<!-- Signed out: only /login reaches here (otherwise the guard redirected). -->
		<div class="flex min-h-[calc(100vh-4rem)] items-center justify-center p-4">
			{@render children()}
		</div>
	{:else}
		<header
			class="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-outline-variant bg-surface-container px-4 md:px-8"
		>
			<a href={resolve('/')} class="flex items-center gap-2 text-lg font-semibold text-primary">
				<img src="/favicon.svg" alt="" class="size-7" />
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
				<span class="hidden text-sm text-on-surface-variant md:inline">
					{$t('nav.signedInAs', { values: { name: currentUser.username } })}
				</span>
				<div bind:this={moreMenu} class="relative md:hidden">
					<button
						class="rounded-full border border-outline-variant p-2 hover:bg-surface-container-high"
						bind:this={moreButton}
						type="button"
						aria-label={$t('nav.more')}
						aria-expanded={moreOpen}
						aria-haspopup="menu"
						onclick={() => (moreOpen = !moreOpen)}
					>
						<span class="text-sm font-semibold" aria-hidden="true"
							>{currentUser.username.slice(0, 1).toUpperCase()}</span
						>
					</button>
					{#if moreOpen}
						<div
							class="absolute right-0 top-12 z-30 min-w-52 rounded-xl border border-outline-variant bg-surface-container p-2 shadow-elevation-3"
							role="menu"
						>
							{#if currentUser.is_admin}
								<a
									href={resolve('/settings')}
									role="menuitem"
									class="block rounded-lg px-3 py-2 text-sm hover:bg-surface-container-high"
									onclick={() => closeMore()}>{$t('nav.settings')}</a
								>
							{/if}
							<button
								type="button"
								role="menuitem"
								class="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-container-high"
								onclick={toggleTheme}
								>{$t('theme.toggle')}<Icon
									icon={theme === 'dark' ? 'theme-light' : 'theme-dark'}
								/></button
							>
							<label class="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm"
								>{$t('language.label')}<select
									class="rounded border border-outline-variant bg-surface px-1 py-0.5"
									value={$locale}
									onchange={onLocaleChange}
									>{#each LOCALES as code (code)}<option value={code}>{code.toUpperCase()}</option
										>{/each}</select
								></label
							>
							<button
								type="button"
								role="menuitem"
								class="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-container-high"
								onclick={handleSignOut}>{$t('nav.signOut')}</button
							>
						</div>
					{/if}
				</div>
				<button
					type="button"
					class="hidden rounded-lg border border-outline-variant px-3 py-1 text-sm font-medium text-on-surface hover:bg-surface-container-high md:block"
					onclick={handleSignOut}
				>
					{$t('nav.signOut')}
				</button>
				<label class="sr-only" for="locale-select">{$t('language.label')}</label>
				<select
					id="locale-select"
					class="hidden rounded-lg border border-outline-variant bg-surface px-2 py-1 text-sm md:block"
					value={$locale}
					onchange={onLocaleChange}
				>
					{#each LOCALES as code (code)}
						<option value={code}>{code.toUpperCase()}</option>
					{/each}
				</select>
				<button
					type="button"
					class="hidden rounded-lg p-2 hover:bg-surface-container-high md:block"
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

			<main class="min-h-[calc(100vh-4rem)] min-w-0 flex-1 p-4 pb-24 md:p-8 md:pb-8">
				{@render children()}
			</main>
		</div>

		<nav
			class="fixed inset-x-0 bottom-0 z-20 flex border-t border-outline-variant bg-surface-container md:hidden"
			aria-label="Main"
		>
			{#each mobileNavItems as item (item.path)}
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
	{/if}

	<Snackbar />
</QueryClientProvider>
