import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { uploadPng } from '../../lib/e2e/uploadPng';

// Search + statistics UI. Verifies a receipt (via the upload flow) so there is
// data, then checks the search and statistics pages render it. The stub's
// generic receipt (merchant "E2E Generic Store", item "Generic Item") is what
// these assertions look for.
const GENERIC_MERCHANT = 'E2E Generic Store';

async function uploadAndVerify(page: Page, request: APIRequestContext) {
	const username = `e2e-ss-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
	const register = await request.post('/api/v1/auth/register', {
		data: { username, password: 'e2e-pw-12345' }
	});
	expect(register.status()).toBe(201);

	await page.goto('/upload');
	await page.setInputFiles('input[type="file"]', uploadPng());
	await page.getByRole('button', { name: 'Upload' }).click();
	// Synchronous analysis: straight to the review page (h1 = merchant).
	await expect(page.getByRole('heading', { name: GENERIC_MERCHANT })).toBeVisible({
		timeout: 30_000
	});
	await page.getByRole('button', { name: 'Verify' }).click();
	const dialog = page.getByRole('dialog', { name: 'Verify receipt?' });
	await expect(dialog).toBeVisible();
	await dialog.getByRole('button', { name: 'Verify' }).click();
	await expect(page.getByText('Receipt verified')).toBeVisible({ timeout: 15_000 });
}

test.describe('search + statistics', () => {
	test('a verified receipt appears in search and statistics', async ({ page, context }) => {
		await uploadAndVerify(page, context.request);

		// Search: the generic item is findable by name.
		await page.goto('/search');
		await page.getByPlaceholder('Search products…').fill('Generic');
		await expect(page.getByText('Generic Item').first()).toBeVisible({ timeout: 15_000 });

		// Statistics: now that a receipt is verified, stats are non-empty.
		await page.goto('/statistics');
		await expect(page.getByText('No statistics yet')).toBeHidden({ timeout: 15_000 });
		await expect(page.getByText('Total spend')).toBeVisible();
	});
});
