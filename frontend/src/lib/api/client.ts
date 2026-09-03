import type {
	AnalyzeResponse,
	ImageCreated,
	ImageListFilters,
	ImageRow,
	ReceiptListFilters,
	ReceiptRow,
	ReceiptWithDetails,
	ReceiptWrite,
	UiConfig
} from '$lib/types';

const API_BASE = (import.meta.env.VITE_API_BASE ?? '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
	status: number;

	detail: string;

	constructor(status: number, detail: string) {
		super(detail);
		this.name = 'ApiError';
		this.status = status;
		this.detail = detail;
	}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`${API_BASE}${path}`, init);
	} catch {
		throw new ApiError(0, 'Network error');
	}

	if (!response.ok) {
		let detail = `${response.status} ${response.statusText}`;
		try {
			const body: unknown = await response.json();
			if (body && typeof body === 'object' && 'detail' in body) {
				const raw = (body as { detail: unknown }).detail;
				detail = typeof raw === 'string' ? raw : JSON.stringify(raw);
			}
		} catch {
			// Non-JSON error body: keep the status text.
		}
		throw new ApiError(response.status, detail);
	}

	if (response.status === 204) {
		return undefined as T;
	}

	return (await response.json()) as T;
}

function toQueryString(params: Record<string, string | number | undefined>): string {
	const parts: string[] = [];
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined || value === '') {
			continue;
		}
		parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
	}
	return parts.length > 0 ? `?${parts.join('&')}` : '';
}

export const api = {
	/**
	 * Upload a receipt image. With `bypassReview` the receipt is persisted
	 * directly as `verified` (no manual review step).
	 */
	async uploadImage(file: File, bypassReview = false): Promise<ImageCreated> {
		const form = new FormData();
		form.append('receipt', file);
		return request<ImageCreated>(
			`/images${toQueryString({ bypass_review: String(bypassReview) })}`,
			{
				method: 'POST',
				body: form
			}
		);
	},

	getUiConfig(): Promise<UiConfig> {
		return request<UiConfig>('/system/ui-config');
	},

	listImages(filters: ImageListFilters = {}): Promise<ImageRow[]> {
		return request<ImageRow[]>(
			`/images${toQueryString({
				status: filters.status?.join(','),
				limit: filters.limit,
				offset: filters.offset
			})}`
		);
	},

	getImage(id: number): Promise<ImageRow> {
		return request<ImageRow>(`/images/${id}`);
	},

	deleteImage(id: number): Promise<void> {
		return request<void>(`/images/${id}`, { method: 'DELETE' });
	},

	analyzePending(): Promise<AnalyzeResponse> {
		return request<AnalyzeResponse>('/images/analyze', { method: 'POST' });
	},

	/** URL for <img> tags / opening in a new tab (not used via fetch). */
	imageFileUrl(id: number): string {
		return `${API_BASE}/images/${id}/file`;
	},

	listReceipts(filters: ReceiptListFilters = {}): Promise<ReceiptRow[]> {
		return request<ReceiptRow[]>(
			`/receipts${toQueryString({
				limit: filters.limit,
				offset: filters.offset,
				status: filters.status?.join(','),
				date_from: filters.date_from,
				date_to: filters.date_to,
				search: filters.search
			})}`
		);
	},

	getReceipt(id: number): Promise<ReceiptWithDetails> {
		return request<ReceiptWithDetails>(`/receipts/${id}`);
	},

	/** PUT /receipts/{id} returns the updated receipt row (without line items). */
	updateReceipt(id: number, body: ReceiptWrite): Promise<ReceiptRow> {
		return request<ReceiptRow>(`/receipts/${id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		});
	},

	/** POST /receipts/{id}/verify returns the verified receipt row (409 if already verified). */
	verifyReceipt(id: number): Promise<ReceiptRow> {
		return request<ReceiptRow>(`/receipts/${id}/verify`, { method: 'POST' });
	},

	/** DELETE /receipts/{id} removes the receipt (and its image). 409 if a benchmark references it. */
	deleteReceipt(id: number): Promise<void> {
		return request<void>(`/receipts/${id}`, { method: 'DELETE' });
	},

	/** GET /tags returns the line-item tag vocabulary (the select source). */
	listTags(): Promise<string[]> {
		return request<string[]>('/tags');
	},

	/**
	 * POST /tags creates (or confirms) a tag. Idempotent: an existing tag is
	 * returned as-is. Returns the normalized name actually stored.
	 */
	createTag(name: string): Promise<{ name: string; created: boolean }> {
		return request<{ name: string; created: boolean }>('/tags', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name })
		});
	}
};
