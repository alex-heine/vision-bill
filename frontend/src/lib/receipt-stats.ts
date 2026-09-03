import type { Category, ReceiptRow } from '$lib/types';

export interface CurrencyTotal {
	currency: string;
	total: number;
}

export interface CategoryTotal extends CurrencyTotal {
	category: Category;
	count: number;
}

function amount(value: string): number {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

export function verifiedReceipts(receipts: ReceiptRow[]): ReceiptRow[] {
	return receipts.filter((receipt) => receipt.status === 'verified');
}

export function totalsByCurrency(receipts: ReceiptRow[]): CurrencyTotal[] {
	const totals = new Map<string, number>();
	for (const receipt of receipts) {
		totals.set(receipt.currency, (totals.get(receipt.currency) ?? 0) + amount(receipt.total));
	}
	return [...totals.entries()]
		.map(([currency, total]) => ({ currency, total }))
		.sort((a, b) => b.total - a.total);
}

export function totalsByCategory(receipts: ReceiptRow[]): CategoryTotal[] {
	const totals = new Map<string, CategoryTotal>();
	for (const receipt of receipts) {
		const key = `${receipt.category}:${receipt.currency}`;
		const current = totals.get(key) ?? {
			category: receipt.category,
			currency: receipt.currency,
			total: 0,
			count: 0
		};
		current.total += amount(receipt.total);
		current.count += 1;
		totals.set(key, current);
	}
	return [...totals.values()].sort((a, b) => b.total - a.total);
}

export function currentMonthReceipts(receipts: ReceiptRow[], today = new Date()): ReceiptRow[] {
	const prefix = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
	return receipts.filter((receipt) => receipt.date.startsWith(prefix));
}
