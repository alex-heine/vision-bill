import { expect, test } from '@playwright/test';
import { uploadPng } from '../../lib/e2e/uploadPng';

// Upload -> analyze -> review -> verify, end to end against the real stack.
// Uploads an in-memory 1x1 PNG; the LLM stub answers synchronously with its
// generic receipt for unknown images, so the upload 201 carries a receipt_id
// and the app routes straight to the receipt review page (h1 = merchant).
const GENERIC_MERCHANT = 'E2E Generic Store';

test.describe('upload flow', () => {
	test('upload a receipt, analyze it, verify it', async ({ page, context }) => {
		// Fresh user (shared cookie jar -> subsequent page.goto is authenticated).
		const username = `e2e-up-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
		const register = await context.request.post('/api/v1/auth/register', {
			data: { username, password: 'e2e-pw-12345' }
		});
		expect(register.status()).toBe(201);

		await page.goto('/upload');
		await page.setInputFiles('input[type="file"]', uploadPng());
		await page.getByRole('button', { name: 'Upload' }).click();

		// Synchronous analysis: the review page shows the merchant as h1 and
		// an unverified receipt offers the Verify button.
		await expect(page.getByRole('heading', { name: GENERIC_MERCHANT })).toBeVisible({
			timeout: 30_000
		});

		// Verify is a two-step confirm: the header button opens a dialog whose
		// confirm button carries the same label — scope to the dialog.
		await page.getByRole('button', { name: 'Verify' }).click();
		const dialog = page.getByRole('dialog', { name: 'Verify receipt?' });
		await expect(dialog).toBeVisible();
		await dialog.getByRole('button', { name: 'Verify' }).click();

		await expect(page.getByText('Receipt verified')).toBeVisible({ timeout: 15_000 });
		// The header badge flips from the Verify button to "Verified".
		await expect(page.getByText('Verified', { exact: true })).toBeVisible();
	});
});
