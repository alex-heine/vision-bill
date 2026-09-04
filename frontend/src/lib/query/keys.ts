import type { ImageListFilters, ReceiptListFilters } from '$lib/types';

export const queryKeys = {
	images: (filters: ImageListFilters = {}) => ['images', filters] as const,
	image: (id: string) => ['images', id] as const,
	receipts: (filters: ReceiptListFilters = {}) => ['receipts', filters] as const,
	receipt: (id: string) => ['receipts', id] as const,
	tags: () => ['tags'] as const,
	uiConfig: () => ['system', 'ui-config'] as const
};
