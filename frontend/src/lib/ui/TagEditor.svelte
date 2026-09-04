<script lang="ts">
	import { t } from '$lib/i18n';
	import { api } from '$lib/api/client';
	import { queryClient } from '$lib/query/client';
	import { queryKeys } from '$lib/query/keys';
	import { snackbar } from '$lib/ui/snackbar.svelte';
	import Icon from './Icon.svelte';

	let {
		value,
		tagOptions,
		id
	}: {
		/** The line item's tags (standard + suggested). Mutated in place. */
		value: string[];
		/** The tag vocabulary loaded from the database. */
		tagOptions: string[];
		/** Unique prefix used to build stable input ids. */
		id: string;
	} = $props();

	const labelClass = 'mb-1 block text-xs font-medium text-on-surface-variant';
	const inputClass =
		'w-full rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2.5 text-sm';

	function isStandard(tag: string): boolean {
		const lower = tag.toLowerCase();
		return tagOptions.some((option) => option.toLowerCase() === lower);
	}

	let standardTags = $derived(value.filter((tag) => isStandard(tag)));
	let suggestedTags = $derived(value.filter((tag) => !isStandard(tag)));

	/** Replace the standard tags while preserving any suggested ones. */
	function setStandardTags(nextStandard: string[]): void {
		const next = [...nextStandard, ...suggestedTags];
		value.length = 0;
		value.push(...next);
	}

	function hasStandardTag(tag: string): boolean {
		return standardTags.some((entry) => entry.toLowerCase() === tag.toLowerCase());
	}

	function toggleStandardTag(tag: string): void {
		const next = hasStandardTag(tag)
			? standardTags.filter((entry) => entry.toLowerCase() !== tag.toLowerCase())
			: [...standardTags, tag];
		setStandardTags(next);
	}

	function removeSuggested(tag: string): void {
		const next = value.filter((entry) => entry !== tag);
		value.length = 0;
		value.push(...next);
	}

	let creating = $state(false);

	async function refreshVocabulary(): Promise<void> {
		await queryClient.invalidateQueries({ queryKey: queryKeys.tags() });
	}

	/** Promote a suggested (non-vocabulary) tag into the standard vocabulary. */
	async function keepSuggested(tag: string): Promise<void> {
		creating = true;
		try {
			await api.createTag(tag);
			await refreshVocabulary();
		} catch {
			snackbar.notify('error', $t('editor.tagsCreateFailed'));
		} finally {
			creating = false;
		}
	}

	let newTagInput = $state('');

	function normalize(input: string): string {
		return input.trim().split(/\s+/).join(' ').toLowerCase();
	}

	// Live filter over the vocabulary so the user can see a match while typing.
	let tagMatches = $derived.by(() => {
		const query = normalize(newTagInput);
		if (!query) return [];
		return tagOptions.filter((option) => option.toLowerCase().includes(query));
	});

	let exactMatch = $derived.by(
		() => tagOptions.find((option) => option.toLowerCase() === normalize(newTagInput)) ?? null
	);

	let addDisabled = $derived(creating || newTagInput.trim() === '');

	async function addTag(): Promise<void> {
		const raw = newTagInput.trim();
		if (raw === '' || creating) return;
		creating = true;
		try {
			const { name } = await api.createTag(raw);
			if (!value.includes(name)) {
				value.push(name);
			}
			newTagInput = '';
			await refreshVocabulary();
		} catch {
			snackbar.notify('error', $t('editor.tagsCreateFailed'));
		} finally {
			creating = false;
		}
	}
</script>

<div class="space-y-3">
	<!-- Standard tags: touch-friendly toggles avoid the native multi-select gesture on mobile. -->
	<div>
		<span id="{id}-tags-label" class={labelClass}>{$t('editor.tagsSelect')}</span>
		<div
			id="{id}-tags-select"
			class="mt-1 flex flex-wrap gap-2"
			role="group"
			aria-labelledby="{id}-tags-label"
		>
			{#each tagOptions as tag (tag)}
				<button
					type="button"
					class="min-h-11 rounded-full border px-3 py-2 text-sm font-medium transition-colors {hasStandardTag(
						tag
					)
						? 'border-primary bg-primary-container text-on-primary-container'
						: 'border-outline-variant bg-surface-container-lowest text-on-surface hover:bg-surface-container-high'}"
					aria-pressed={hasStandardTag(tag)}
					onclick={() => toggleStandardTag(tag)}
				>
					{tag}
				</button>
			{/each}
		</div>
	</div>

	<!-- Suggested tags (present on the item but not in the vocabulary) -->
	{#if suggestedTags.length > 0}
		<div>
			<span class={labelClass}>{$t('editor.tagsSuggested')}</span>
			<div class="flex flex-wrap gap-2">
				{#each suggestedTags as tag (tag)}
					<span
						class="inline-flex items-center gap-1.5 rounded-full border border-warning/50 bg-warning/10 py-1 pl-3 pr-1.5 text-xs font-medium text-on-surface"
					>
						<span
							class="rounded-full bg-warning px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-on-warning"
							>{$t('editor.tagsSuggestedBadge')}</span
						>
						{tag}
						<button
							type="button"
							class="flex min-h-11 min-w-11 items-center justify-center rounded-full p-2 text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
							title={$t('editor.tagsKeep')}
							aria-label={$t('editor.tagsKeep')}
							disabled={creating}
							onclick={() => keepSuggested(tag)}
						>
							<Icon icon="check" />
						</button>
						<button
							type="button"
							class="flex min-h-11 min-w-11 items-center justify-center rounded-full p-2 text-on-surface-variant hover:bg-error-container hover:text-on-error-container"
							title={$t('editor.tagsRemove')}
							aria-label={$t('editor.tagsRemove')}
							disabled={creating}
							onclick={() => removeSuggested(tag)}
						>
							<Icon icon="close" />
						</button>
					</span>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Add a new tag (with live vocabulary filter + exists/new hint) -->
	<div>
		<label class={labelClass} for="{id}-tags-add">{$t('editor.tagsAdd')}</label>
		<div class="relative">
			<div class="flex flex-col gap-2 sm:flex-row">
				<input
					id="{id}-tags-add"
					class={inputClass}
					placeholder={$t('editor.tagsAddPlaceholder')}
					value={newTagInput}
					oninput={(e) => (newTagInput = (e.currentTarget as HTMLInputElement).value)}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							e.preventDefault();
							void addTag();
						}
					}}
				/>
				<button
					type="button"
					class="flex min-h-11 w-full shrink-0 items-center justify-center gap-1.5 rounded-lg bg-secondary-container px-3 py-2 text-sm font-medium text-on-secondary-container hover:opacity-90 disabled:opacity-50 sm:w-auto"
					disabled={addDisabled}
					onclick={() => addTag()}
				>
					<Icon icon="plus" />
					{$t('editor.tagsAddButton')}
				</button>
			</div>

			{#if newTagInput.trim() !== '' && tagMatches.length > 0}
				<div
					class="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest shadow-elevation-2"
				>
					{#each tagMatches.slice(0, 6) as match (match)}
						<button
							type="button"
							class="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-surface-container"
							onclick={() => (newTagInput = match)}
						>
							<span>{match}</span>
							<span class="text-xs text-on-surface-variant">{$t('editor.tagsExisting')}</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		{#if newTagInput.trim() !== ''}
			{#if exactMatch}
				<p class="mt-1 text-xs text-on-surface-variant">
					{$t('editor.tagsExistsHint', { values: { tag: exactMatch } })}
				</p>
			{:else}
				<p class="mt-1 text-xs text-on-surface-variant">{$t('editor.tagsNewHint')}</p>
			{/if}
		{/if}
	</div>
</div>
