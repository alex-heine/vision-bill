import { expect, test } from '@playwright/test';
import { registerUser } from '../helpers/auth';

test.describe('auth guards', () => {
	test('signed-out user is bounced to /login', async ({ page }) => {
		await page.goto('/receipts');
		await expect(page).toHaveURL(/\/login$/);
	});

	test('signed-in user on /login is bounced to the dashboard', async ({
		page,
		context,
		baseURL
	}) => {
		await registerUser(context, 'e2e-guard');
		await page.goto('/login');
		await expect(page).toHaveURL(baseURL + '/');
	});

	test('session survives a reload', async ({ page, context }) => {
		await registerUser(context, 'e2e-guard');
		await page.goto('/');
		await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
		await page.reload();
		await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
		await expect(page).not.toHaveURL(/\/login/);
	});

	test('non-admin /settings redirects home', async ({ page, context, baseURL }) => {
		await registerUser(context, 'e2e-guard');
		await page.goto('/settings');
		await expect(page).toHaveURL(baseURL + '/');
	});

	// EXPECTED RED #1 — /benchmarks has no admin redirect guard yet (the form
	// renders and the create call fails with a raw 403). Stays red by design.
	test('non-admin /benchmarks redirects home', async ({ page, context, baseURL }) => {
		await registerUser(context, 'e2e-guard');
		await page.goto('/benchmarks');
		await expect(page).toHaveURL(baseURL + '/');
	});

	// EXPECTED RED #2 — same gap on the results page (raw "Unable to load
	// benchmark runs." error instead of a redirect). Stays red by design.
	test('non-admin /benchmarks/results redirects home', async ({ page, context, baseURL }) => {
		await registerUser(context, 'e2e-guard');
		await page.goto('/benchmarks/results');
		await expect(page).toHaveURL(baseURL + '/');
	});
});
