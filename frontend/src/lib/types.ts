export type ImageStatus = 'pending' | 'analyzed' | 'failed';

export type ReceiptStatus = 'unverified' | 'verified';

export type Category =
	| 'grocery'
	| 'electronics'
	| 'clothing'
	| 'restaurant'
	| 'fuel'
	| 'pharmacy'
	| 'entertainment'
	| 'other';

export type PaymentMethod =
	'cash' | 'credit_card' | 'debit_card' | 'mobile_payment' | 'check' | 'other' | 'unknown';

export interface ImageRow {
	id: number;
	original_filename: string | null;
	media_type: string | null;
	size_bytes: number | null;
	image_path: string | null;
	status: ImageStatus;
	error: string | null;
	receipt_id: number | null;
	created_at: string | null;
	analyzed_at: string | null;
}

export interface ReceiptRow {
	id: number;
	confidence: number;
	merchant_name: string;
	merchant_address: string | null;
	receipt_number: string | null;
	/** ISO date, YYYY-MM-DD */
	date: string;
	/** HH:MM 24h */
	time: string | null;
	currency: string;
	category: Category;
	subtotal: string;
	discount_total: string;
	tax_total: string;
	tip: string | null;
	total: string;
	payment_method: PaymentMethod;
	/** ISO date, YYYY-MM-DD */
	created_at: string | null;
	status: ReceiptStatus;
	image_id: number | null;
	verified: boolean;
}

export interface LineItemRow {
	id: number;
	receipt_id: number;
	description: string;
	quantity: number;
	unit_price: string;
	total_price: string;
	category: Category;
	tags: string[];
}

export interface TaxLineRow {
	id: number;
	receipt_id: number;
	name: string;
	rate: number | null;
	amount: string;
}

export interface ReceiptWithDetails {
	receipt: ReceiptRow;
	line_items: LineItemRow[];
	taxes: TaxLineRow[];
	image_path: string | null;
}

/** Body for POST /images (file uploaded via FormData, model_id as query param). */
export interface ImageCreated {
	image_id: number;
	status: ImageStatus;
	receipt_id?: number | null;
	warning?: string;
	original_filename?: string;
	media_type?: string;
	size_bytes?: number;
	image_path?: string;
}

/** Safe server-side defaults that affect browser workflow. */
export interface UiConfig {
	bypass_review_default: boolean;
}

export interface LineItemWrite {
	description: string;
	quantity: number;
	unit_price: string;
	total_price: string;
	category?: Category;
	tags?: string[];
}

export interface TaxLineWrite {
	name: string;
	rate?: number | null;
	amount: string;
}

/** Body for PUT /receipts/{id} (mirrors the backend `Receipt` write model). */
export interface ReceiptWrite {
	confidence: number;
	merchant_name: string;
	merchant_address?: string | null;
	receipt_number?: string | null;
	/** ISO date, YYYY-MM-DD */
	date: string;
	time?: string | null;
	currency?: string;
	category?: Category;
	line_items: LineItemWrite[];
	taxes?: TaxLineWrite[];
	subtotal: string;
	discount_total?: string;
	tax_total?: string;
	tip?: string | null;
	total: string;
	payment_method?: PaymentMethod;
}

/** One result of POST /images/analyze (backend PendingImageResult). */
export interface PendingImageResult {
	image_id: number;
	status: 'analyzed' | 'failed';
	receipt_id?: number | null;
	error?: string | null;
}

export interface AnalyzeResponse {
	results: PendingImageResult[];
}

export interface ReceiptListFilters {
	limit?: number;
	offset?: number;
	status?: ReceiptStatus[];
	/** ISO date, YYYY-MM-DD (inclusive) */
	date_from?: string;
	/** ISO date, YYYY-MM-DD (inclusive) */
	date_to?: string;
	search?: string;
}

export interface ImageListFilters {
	status?: ImageStatus[];
	limit?: number;
	offset?: number;
}
