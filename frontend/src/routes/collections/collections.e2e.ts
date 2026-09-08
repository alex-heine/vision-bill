import { expect, test } from '@playwright/test';

// End-to-end smoke test for the collections feature, run against an
// already-running vision-bill app (see playwright.config.ts for the base URL).
// A fresh user is registered per run so the suite is isolated from any
// existing data; registration is the only auth path needed (it is open by
// default).
test.describe('collections', () => {
	test('create a collection, open it, and see the statistics filter', async ({ page, context }) => {
		// Register a fresh, isolated user. context.request shares the browser
		// context's cookie jar, so the vb_session Set-Cookie from this response
		// is stored automatically and sent on every subsequent navigation — no
		// manual cookie transfer is needed.
		const username = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
		const register = await context.request.post('/api/v1/auth/register', {
			data: { username, password: 'e2e-password-123' }
		});
		expect(register.status()).toBe(201);

		// Create a collection via the overview page dialog.
		await page.goto('/collections');
		await page.getByRole('button', { name: /New collection/i }).click();
		await page.getByLabel(/Name/i).fill('Berlin Trip');
		await page.getByRole('button', { name: /Save/i }).click();
		await expect(page.getByText('Berlin Trip').first()).toBeVisible();

		// Open the collection and confirm the (empty) receipts section renders.
		await page.getByRole('link', { name: /Berlin Trip/i }).click();
		await expect(page.getByText(/Receipts|No receipts in this collection/i).first()).toBeVisible();

		// The statistics page exposes the collection filter.
		await page.goto('/statistics');
		await expect(page.getByText(/Collection/).first()).toBeVisible();
	});
});
