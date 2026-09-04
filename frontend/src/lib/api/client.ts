import type {
	AnalyzeResponse,
	ImageCreated,
	ImageListFilters,
	ImageRow,
	ReceiptListFilters,
	ReceiptRow,
	ReceiptStatistics,
	ReceiptWithDetails,
	ReceiptWrite,
	SettingsUpdate,
	SettingsView,
	User,
	UiConfig
} from '$lib/types';

const API_BASE = (import.meta.env.VITE_API_BASE ?? '/api/v1').replace(/\/$/, '');

/**
 * Handler invoked on any 401 from a protected (non-`/auth/`) endpoint. Wired up
 * by `$lib/auth` to drop the session and redirect to the login page. Kept as a
 * swappable callback so this module never imports the session store (no cycle).
 */
let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: () => void): void {
	unauthorizedHandler = handler;
}

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
		// same-origin so the HttpOnly session cookie is sent automatically.
		response = await fetch(`${API_BASE}${path}`, { credentials: 'same-origin', ...init });
	} catch {
		throw new ApiError(0, 'Network error');
	}

	if (!response.ok) {
		// A 401 on a protected endpoint means the session expired: bounce to
		// login. The /auth/ endpoints 401 for bad credentials, not an expired
		// session, so they are excluded.
		if (response.status === 401 && !path.startsWith('/auth/')) {
			unauthorizedHandler?.();
		}
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

	getStatistics(weeks = 12): Promise<ReceiptStatistics> {
		return request<ReceiptStatistics>(`/statistics${toQueryString({ weeks })}`);
	},

	getSettings(): Promise<SettingsView> {
		return request<SettingsView>('/system/settings');
	},

	updateSettings(body: SettingsUpdate): Promise<SettingsView> {
		return request<SettingsView>('/system/settings', {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				llm: body.llm,
				allow_registration: body.allow_registration
			})
		});
	},

	/** GET /auth/me returns the current user (401 when the session is gone). */
	me(): Promise<User> {
		return request<User>('/auth/me');
	},

	/** POST /auth/login authenticates and sets the session cookie. */
	login(username: string, password: string): Promise<User> {
		return request<User>('/auth/login', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ username, password })
		});
	},

	/** POST /auth/register creates an account (403 if registration is disabled). */
	register(username: string, password: string): Promise<User> {
		return request<User>('/auth/register', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ username, password })
		});
	},

	/** POST /auth/logout clears the session cookie. */
	logout(): Promise<void> {
		return request<void>('/auth/logout', { method: 'POST' });
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

	getImage(id: string): Promise<ImageRow> {
		return request<ImageRow>(`/images/${id}`);
	},

	deleteImage(id: string): Promise<void> {
		return request<void>(`/images/${id}`, { method: 'DELETE' });
	},

	analyzePending(): Promise<AnalyzeResponse> {
		return request<AnalyzeResponse>('/images/analyze', { method: 'POST' });
	},

	/** URL for <img> tags / opening in a new tab (not used via fetch). */
	imageFileUrl(id: string): string {
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

	getReceipt(id: string): Promise<ReceiptWithDetails> {
		return request<ReceiptWithDetails>(`/receipts/${id}`);
	},

	/** PUT /receipts/{id} returns the updated receipt row (without line items). */
	updateReceipt(id: string, body: ReceiptWrite): Promise<ReceiptRow> {
		return request<ReceiptRow>(`/receipts/${id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		});
	},

	/** POST /receipts/{id}/verify returns the verified receipt row (409 if already verified). */
	verifyReceipt(id: string): Promise<ReceiptRow> {
		return request<ReceiptRow>(`/receipts/${id}/verify`, { method: 'POST' });
	},

	/** DELETE /receipts/{id} removes the receipt (and its image). 409 if a benchmark references it. */
	deleteReceipt(id: string): Promise<void> {
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
