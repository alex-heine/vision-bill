import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from './client';
import { queryKeys } from '../query/keys';

const OK_BODY = {
	query: 'Schinken',
	purchases: [
		{
			receipt_id: '6f1e0c1a-0000-4000-8000-000000000001',
			description: 'Schinken natur',
			merchant_name: 'REWE',
			date: '2026-08-30',
			time: '18:42',
			quantity: 1.0,
			unit_price: '4.99',
			currency: 'EUR'
		}
	],
	latest_price: '4.99',
	cheapest_price: '4.29',
	average_price: '4.64',
	currency: 'EUR'
};

function mockOkFetch(): void {
	vi.stubGlobal(
		'fetch',
		vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			statusText: 'OK',
			json: async () => OK_BODY
		})
	);
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('api.searchProducts', () => {
	it('GETs /search with the url-encoded query and returns the parsed body', async () => {
		mockOkFetch();

		const result = await api.searchProducts('Schinken');

		const fetchMock = vi.mocked(fetch);
		expect(fetchMock).toHaveBeenCalledOnce();
		const [url, init] = fetchMock.mock.calls[0];
		expect(String(url)).toContain('/search?query=Schinken');
		expect(init).toEqual({ credentials: 'same-origin' });
		expect(result).toEqual(OK_BODY);
	});

	it('url-encodes special characters in the term', async () => {
		mockOkFetch();

		await api.searchProducts('a b&c');

		const [url] = vi.mocked(fetch).mock.calls[0];
		expect(String(url)).toContain('/search?query=a%20b%26c');
	});
});

describe('queryKeys.search', () => {
	it('builds a per-term key', () => {
		expect(queryKeys.search('Schinken')).toEqual(['search', 'Schinken']);
		expect(queryKeys.search('a')).not.toEqual(queryKeys.search('b'));
	});
});
