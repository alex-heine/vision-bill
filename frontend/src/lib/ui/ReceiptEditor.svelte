<script lang="ts">
	import { SvelteSet } from 'svelte/reactivity';
	import { createQuery } from '@tanstack/svelte-query';
	import { t } from '$lib/i18n';
	import { api } from '$lib/api/client';
	import { queryClient } from '$lib/query/client';
	import { queryKeys } from '$lib/query/keys';
	import { formatMoney, isPlainDecimal } from '$lib/ui/money';
	import Icon from '$lib/ui/Icon.svelte';
	import TagEditor from '$lib/ui/TagEditor.svelte';
	import type {
		Category,
		LineItemRow,
		PaymentMethod,
		ReceiptRow,
		ReceiptWrite,
		TaxLineRow
	} from '$lib/types';

	const CATEGORIES: Category[] = [
		'grocery',
		'electronics',
		'clothing',
		'restaurant',
		'fuel',
		'pharmacy',
		'entertainment',
		'other'
	];

	const PAYMENT_METHODS: PaymentMethod[] = [
		'cash',
		'credit_card',
		'debit_card',
		'mobile_payment',
		'check',
		'other',
		'unknown'
	];

	const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

	/** All form values are strings (amounts travel as decimal strings). */
	interface EditorLine {
		description: string;
		quantity: string;
		unit_price: string;
		total_price: string;
		category: string;
		tags: string[];
	}

	interface EditorTax {
		name: string;
		rate: string;
		amount: string;
	}

	interface EditorForm {
		confidence: string;
		merchant_name: string;
		merchant_address: string;
		receipt_number: string;
		date: string;
		time: string;
		currency: string;
		category: string;
		payment_method: string;
		subtotal: string;
		discount_total: string;
		tax_total: string;
		tip: string;
		total: string;
		lines: EditorLine[];
		taxLines: EditorTax[];
	}

	function buildForm(
		receipt: ReceiptRow,
		lineItems: LineItemRow[],
		taxes: TaxLineRow[]
	): EditorForm {
		return {
			confidence: String(receipt.confidence),
			merchant_name: receipt.merchant_name,
			merchant_address: receipt.merchant_address ?? '',
			receipt_number: receipt.receipt_number ?? '',
			date: receipt.date,
			time: receipt.time ?? '',
			currency: receipt.currency || 'USD',
			category: receipt.category,
			payment_method: receipt.payment_method,
			subtotal: String(receipt.subtotal),
			discount_total: String(receipt.discount_total),
			tax_total: String(receipt.tax_total),
			tip: receipt.tip === null ? '' : String(receipt.tip),
			total: String(receipt.total),
			lines: lineItems.map((line) => ({
				description: line.description,
				quantity: String(line.quantity),
				unit_price: String(line.unit_price),
				total_price: String(line.total_price),
				category: line.category,
				tags: [...(line.tags ?? [])]
			})),
			taxLines: taxes.map((tax) => ({
				name: tax.name,
				rate: tax.rate === null ? '' : String(tax.rate),
				amount: String(tax.amount)
			}))
		};
	}

	let {
		receipt,
		lineItems,
		taxes,
		busy = false,
		onSave,
		onSaveAndVerify,
		onDirtyChange
	}: {
		receipt: ReceiptRow;
		lineItems: LineItemRow[];
		taxes: TaxLineRow[];
		/** Disable the action buttons while a request is in flight. */
		busy?: boolean;
		/** Offered when the page wants a plain save (no verify). */
		onSave?: (write: ReceiptWrite) => void;
		/** Offered when the receipt can still be verified. */
		onSaveAndVerify?: (write: ReceiptWrite) => void;
		/** Notified with the current dirty state after (re)initialisation. */
		onDirtyChange?: (dirty: boolean) => void;
	} = $props();

	function initialForm(): EditorForm {
		return buildForm(receipt, lineItems, taxes);
	}

	let form = $state<EditorForm>(initialForm());
	let snapshot = $state<EditorForm>(initialForm());
	let initializedReceiptId: number | undefined;

	// Tag vocabulary (the <select> source), fetched once per editor mount.
	const tagList = createQuery(
		() => ({ queryKey: queryKeys.tags(), queryFn: () => api.listTags() }),
		() => queryClient
	);
	let tagOptions = $derived<string[]>(tagList.data ?? []);

	$effect(() => {
		if (receipt.id !== initializedReceiptId) {
			initializedReceiptId = receipt.id;
			const fresh = initialForm();
			form = fresh;
			snapshot = fresh;
		}
	});

	let dirty = $derived(JSON.stringify(form) !== JSON.stringify(snapshot));
	$effect(() => {
		onDirtyChange?.(dirty);
	});

	const REQUIRED_AMOUNTS = ['subtotal', 'total'] as const;
	const OPTIONAL_AMOUNTS = ['discount_total', 'tax_total', 'tip'] as const;

	let errors = $derived.by(() => {
		const set = new SvelteSet<string>();
		if (!form.merchant_name.trim()) {
			set.add('editor.merchantRequired');
		}
		if (!DATE_RE.test(form.date)) {
			set.add('editor.dateRequired');
		}
		for (const key of REQUIRED_AMOUNTS) {
			if (!isPlainDecimal(form[key])) {
				set.add('editor.invalidAmount');
			}
		}
		for (const key of OPTIONAL_AMOUNTS) {
			if (form[key].trim() !== '' && !isPlainDecimal(form[key])) {
				set.add('editor.invalidAmount');
			}
		}
		const confidence = Number(form.confidence);
		if (
			form.confidence.trim() === '' ||
			!Number.isInteger(confidence) ||
			confidence < 0 ||
			confidence > 100
		) {
			set.add('editor.invalidConfidence');
		}
		for (const line of form.lines) {
			const quantity = Number(line.quantity);
			if (line.quantity.trim() === '' || !Number.isFinite(quantity) || quantity <= 0) {
				set.add('editor.invalidQuantity');
			}
			if (!isPlainDecimal(line.unit_price) || !isPlainDecimal(line.total_price)) {
				set.add('editor.invalidAmount');
			}
		}
		for (const tax of form.taxLines) {
			if (!isPlainDecimal(tax.amount)) {
				set.add('editor.invalidAmount');
			}
			if (tax.rate.trim() !== '') {
				const rate = Number(tax.rate);
				if (!Number.isFinite(rate) || rate < 0 || rate > 1) {
					set.add('editor.invalidRate');
				}
			}
		}
		return [...set];
	});
	let valid = $derived(errors.length === 0);

	/** Subtotal − discount + tax + tip, computed with exact decimal math. */
	let expectedTotal = $derived.by((): number | null => {
		const subtotal = form.subtotal.trim();
		if (!isPlainDecimal(subtotal)) {
			return null;
		}
		const discount = form.discount_total.trim() || '0';
		const taxTotal = form.tax_total.trim() || '0';
		const tip = form.tip.trim() || '0';
		if (!isPlainDecimal(discount) || !isPlainDecimal(taxTotal) || !isPlainDecimal(tip)) {
			return null;
		}
		return parseFloat(subtotal) - parseFloat(discount) + parseFloat(taxTotal) + parseFloat(tip);
	});

	let totalMismatch = $derived.by((): number | null => {
		if (expectedTotal === null) {
			return null;
		}
		const entered = Number(form.total.trim());
		if (!Number.isFinite(entered)) {
			return null;
		}
		const diff = Math.abs(expectedTotal - entered);
		return diff > 0.05 ? diff : null;
	});

	let hasActions = $derived(Boolean(onSave) || Boolean(onSaveAndVerify));

	function buildWrite(): ReceiptWrite {
		return {
			confidence: Number(form.confidence),
			merchant_name: form.merchant_name.trim(),
			merchant_address: form.merchant_address.trim() || null,
			receipt_number: form.receipt_number.trim() || null,
			date: form.date,
			time: form.time.trim() || null,
			currency: form.currency.trim().toUpperCase() || 'USD',
			category: form.category as Category,
			line_items: form.lines.map((line) => ({
				description: line.description.trim(),
				quantity: Number(line.quantity),
				unit_price: line.unit_price.trim(),
				total_price: line.total_price.trim(),
				category: line.category as Category,
				tags: line.tags.map((tag) => tag.trim()).filter((tag) => tag.length > 0)
			})),
			taxes: form.taxLines.map((tax) => ({
				name: tax.name.trim(),
				rate: tax.rate.trim() === '' ? null : Number(tax.rate),
				amount: tax.amount.trim()
			})),
			subtotal: form.subtotal.trim(),
			discount_total: form.discount_total.trim() || '0',
			tax_total: form.tax_total.trim() || '0',
			tip: form.tip.trim() === '' ? null : form.tip.trim(),
			total: form.total.trim(),
			payment_method: form.payment_method as PaymentMethod
		};
	}

	function addLine() {
		form.lines.push({
			description: '',
			quantity: '1',
			unit_price: '',
			total_price: '',
			category: 'other',
			tags: []
		});
	}

	function removeLine(index: number) {
		form.lines.splice(index, 1);
	}

	function addTax() {
		form.taxLines.push({ name: '', rate: '', amount: '' });
	}

	function removeTax(index: number) {
		form.taxLines.splice(index, 1);
	}

	const labelClass = 'mb-1 block text-xs font-medium text-on-surface-variant';
	const inputClass =
		'w-full rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2.5 text-sm';
</script>

<section class="space-y-6">
	<!-- Details -->
	<div class="rounded-xl border border-outline-variant bg-surface-container-low p-4">
		<h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
			{$t('editor.details')} -
			<label class={labelClass} for="re-confidence"
				>{$t('editor.confidence')}: {form.confidence}</label
			>
		</h2>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			<div class="sm:col-span-2">
				<label class={labelClass} for="re-merchant">{$t('editor.merchant')}</label>
				<input
					id="re-merchant"
					class={inputClass}
					value={form.merchant_name}
					oninput={(e) => (form.merchant_name = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div class="sm:col-span-2">
				<label class={labelClass} for="re-address">{$t('editor.address')}</label>
				<input
					id="re-address"
					class={inputClass}
					value={form.merchant_address}
					oninput={(e) => (form.merchant_address = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div>
				<label class={labelClass} for="re-number">{$t('editor.number')}</label>
				<input
					id="re-number"
					class={inputClass}
					value={form.receipt_number}
					oninput={(e) => (form.receipt_number = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div>
				<label class={labelClass} for="re-date">{$t('editor.date')}</label>
				<input
					id="re-date"
					type="date"
					class={inputClass}
					value={form.date}
					oninput={(e) => (form.date = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div>
				<label class={labelClass} for="re-time">{$t('editor.time')}</label>
				<input
					id="re-time"
					type="time"
					class={inputClass}
					value={form.time}
					oninput={(e) => (form.time = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div>
				<label class={labelClass} for="re-currency">{$t('editor.currency')}</label>
				<input
					id="re-currency"
					class={inputClass}
					placeholder="EUR"
					value={form.currency}
					oninput={(e) => (form.currency = (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
			<div>
				<label class={labelClass} for="re-category">{$t('editor.category')}</label>
				<select
					id="re-category"
					class={inputClass}
					value={form.category}
					onchange={(e) => (form.category = (e.currentTarget as HTMLSelectElement).value)}
				>
					{#each CATEGORIES as category (category)}
						<option value={category}>{$t(`categories.${category}`)}</option>
					{/each}
				</select>
			</div>
			<div>
				<label class={labelClass} for="re-payment">{$t('editor.paymentMethod')}</label>
				<select
					id="re-payment"
					class={inputClass}
					value={form.payment_method}
					onchange={(e) => (form.payment_method = (e.currentTarget as HTMLSelectElement).value)}
				>
					{#each PAYMENT_METHODS as method (method)}
						<option value={method}>{$t(`payment.${method}`)}</option>
					{/each}
				</select>
			</div>
		</div>
	</div>

	<!-- Amounts -->
	<div class="rounded-xl border border-outline-variant bg-surface-container-low p-4">
		<h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
			{$t('editor.amounts')}
		</h2>
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
			{#each [['subtotal', 'editor.subtotal'], ['discount_total', 'editor.discount'], ['tax_total', 'editor.taxTotal'], ['tip', 'editor.tip'], ['total', 'editor.total']] as [field, labelKey] (field)}
				<div class={field === 'total' ? 'col-span-2 sm:col-span-3' : ''}>
					<label class={labelClass} for="re-{field}">{$t(labelKey)}</label>
					<input
						id="re-{field}"
						inputmode="decimal"
						class="{inputClass} {field === 'total' ? 'font-semibold' : ''}"
						value={form[field as 'subtotal' | 'discount_total' | 'tax_total' | 'tip' | 'total']}
						oninput={(e) => {
							const target = e.currentTarget as HTMLInputElement;
							form[field as 'subtotal' | 'discount_total' | 'tax_total' | 'tip' | 'total'] =
								target.value;
						}}
					/>
				</div>
			{/each}
		</div>
		{#if expectedTotal !== null}
			<p class="mt-3 text-sm text-on-surface-variant">
				{$t('editor.expectedTotal')}:
				<span class="font-medium">{expectedTotal} {form.currency}</span>
				{#if totalMismatch !== null}
					<span class="ml-2 font-medium text-error">
						{$t('editor.totalMismatch', {
							values: { diff: formatMoney(totalMismatch, form.currency) }
						})}
					</span>
				{/if}
			</p>
		{/if}
	</div>

	<!-- Line items -->
	<div class="rounded-xl border border-outline-variant bg-surface-container-low p-4">
		<div class="mb-3 flex items-center justify-between">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
				{$t('editor.lineItems')}
			</h2>
			<button
				type="button"
				class="flex items-center gap-1.5 rounded-lg bg-secondary-container px-3 py-2 text-sm font-medium text-on-secondary-container hover:opacity-90"
				onclick={addLine}
			>
				<Icon icon="plus" />
				{$t('editor.addItem')}
			</button>
		</div>
		{#if form.lines.length === 0}
			<p class="text-sm text-on-surface-variant">{$t('editor.noLineItems')}</p>
		{:else}
			<div class="space-y-3">
				{#each form.lines as line, index (index)}
					<div class="rounded-lg border border-outline-variant bg-surface-container-lowest p-3">
						<div class="flex items-start gap-2">
							<input
								class="{inputClass} flex-1"
								aria-label={$t('editor.description')}
								placeholder={$t('editor.description')}
								value={line.description}
								oninput={(e) => (line.description = (e.currentTarget as HTMLInputElement).value)}
							/>
							<button
								type="button"
								class="rounded-lg p-2 text-on-surface-variant hover:bg-error-container hover:text-on-error-container"
								aria-label={$t('common.remove')}
								onclick={() => removeLine(index)}
							>
								<Icon icon="trash" />
							</button>
						</div>
						<div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
							<div>
								<label class={labelClass} for="li-{index}-qty">{$t('editor.quantity')}</label>
								<input
									id="li-{index}-qty"
									inputmode="decimal"
									class={inputClass}
									value={line.quantity}
									oninput={(e) => (line.quantity = (e.currentTarget as HTMLInputElement).value)}
								/>
							</div>
							<div>
								<label class={labelClass} for="li-{index}-unit">{$t('editor.unitPrice')}</label>
								<input
									id="li-{index}-unit"
									inputmode="decimal"
									class={inputClass}
									value={line.unit_price}
									oninput={(e) => (line.unit_price = (e.currentTarget as HTMLInputElement).value)}
								/>
							</div>
							<div>
								<label class={labelClass} for="li-{index}-total">{$t('editor.totalPrice')}</label>
								<input
									id="li-{index}-total"
									inputmode="decimal"
									class={inputClass}
									value={line.total_price}
									oninput={(e) => (line.total_price = (e.currentTarget as HTMLInputElement).value)}
								/>
							</div>
							<div class="col-span-2 sm:col-span-4">
								<TagEditor value={line.tags} {tagOptions} id={`li-${index}`} />
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Taxes -->
	<div class="rounded-xl border border-outline-variant bg-surface-container-low p-4">
		<div class="mb-3 flex items-center justify-between">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
				{$t('editor.taxes')}
			</h2>
			<button
				type="button"
				class="flex items-center gap-1.5 rounded-lg bg-secondary-container px-3 py-2 text-sm font-medium text-on-secondary-container hover:opacity-90"
				onclick={addTax}
			>
				<Icon icon="plus" />
				{$t('editor.addTax')}
			</button>
		</div>
		{#if form.taxLines.length === 0}
			<p class="text-sm text-on-surface-variant">{$t('editor.noTaxes')}</p>
		{:else}
			<div class="space-y-2">
				{#each form.taxLines as tax, index (index)}
					<div class="grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_8rem_10rem_2.5rem]">
						<div>
							<label class={labelClass} for="tax-{index}-name">{$t('editor.taxName')}</label>
							<input
								id="tax-{index}-name"
								class={inputClass}
								value={tax.name}
								oninput={(e) => (tax.name = (e.currentTarget as HTMLInputElement).value)}
							/>
						</div>
						<div>
							<label class={labelClass} for="tax-{index}-rate">{$t('editor.taxRate')}</label>
							<input
								id="tax-{index}-rate"
								inputmode="decimal"
								class={inputClass}
								value={tax.rate}
								oninput={(e) => (tax.rate = (e.currentTarget as HTMLInputElement).value)}
							/>
						</div>
						<div>
							<label class={labelClass} for="tax-{index}-amount">{$t('editor.amount')}</label>
							<input
								id="tax-{index}-amount"
								inputmode="decimal"
								class={inputClass}
								value={tax.amount}
								oninput={(e) => (tax.amount = (e.currentTarget as HTMLInputElement).value)}
							/>
						</div>
						<button
							type="button"
							class="rounded-lg p-2.5 text-on-surface-variant hover:bg-error-container hover:text-on-error-container"
							aria-label={$t('common.remove')}
							onclick={() => removeTax(index)}
						>
							<Icon icon="trash" />
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Action bar -->
	{#if hasActions && dirty}
		<div
			class="sticky bottom-20 md:bottom-0 space-y-3 rounded-xl border border-outline-variant bg-surface-container p-4 shadow-elevation-2"
		>
			{#if errors.length > 0}
				<ul class="space-y-1" role="alert">
					{#each errors as error (error)}
						<li class="flex items-center gap-2 text-sm text-error">
							<Icon icon="alert" />
							{$t(error)}
						</li>
					{/each}
				</ul>
			{/if}
			<div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
				{#if dirty && onSave}
					<button
						type="button"
						class="rounded-lg border border-outline-variant px-4 py-2.5 text-sm font-medium text-on-surface hover:bg-surface-container-high disabled:opacity-50"
						disabled={busy || !valid}
						onclick={() => onSave(buildWrite())}
					>
						{$t('common.save')}
					</button>
				{/if}
				{#if onSaveAndVerify !== undefined}
					<button
						type="button"
						class="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
						disabled={busy || !valid}
						onclick={() => onSaveAndVerify(buildWrite())}
					>
						<Icon icon="check" />
						{$t('editor.saveAndVerify')}
					</button>
				{/if}
			</div>
		</div>
	{/if}
</section>
