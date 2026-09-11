import { expect, test } from '@playwright/test';
import { registerUser } from '../helpers/auth';
import { loadFixture } from '../helpers/fixtures';
import { stubGuard } from '../helpers/stub';
import { uploadFixture } from '../helpers/ui';

test.describe('adversarial inputs (browser-level)', () => {
	stubGuard();

	test('hostile collection name renders as inert text', async ({ page, context }) => {
		test.setTimeout(120_000);
		await registerUser(context, 'e2e-xss');
		const payload = '<img src=x onerror=alert(1)>';
		const errors: string[] = [];
		page.on('pageerror', (err) => errors.push(String(err)));

		await page.goto('/collections');
		await page.getByRole('button', { name: 'New collection' }).click();
		const dialog = page.getByRole('dialog', { name: 'New collection' });
		await dialog.getByLabel('Name').fill(payload);
		await dialog.getByRole('button', { name: 'Save' }).click();

		// Rendered as literal text (Svelte auto-escaping), nothing executed.
		await expect(page.getByText(payload)).toBeVisible();
		expect(errors).toHaveLength(0);
	});

	test('hostile merchant renders as inert text in list and detail', async ({ page, context }) => {
		test.setTimeout(120_000);
		const fixture = await loadFixture('b');
		await uploadFixture(page, context, fixture, { verify: false });
		const payload = `Bob's "<b>Bold</b>" & Coffee`;
		await page.locator('#re-merchant').fill(payload);
		await page.getByRole('button', { name: 'Save', exact: true }).click();
		await expect(page.getByText('Changes saved')).toBeVisible({ timeout: 15_000 });

		await page.goto('/receipts');
		await expect(page.getByText(payload)).toBeVisible();
		await page.locator('a[href^="/receipts/"]').first().click();
		await expect(page.getByRole('heading', { name: payload })).toBeVisible();
	});

	test('path-traversal style receipt url does not crash', async ({ page, context }) => {
		await registerUser(context, 'e2e-xss');
		await page.goto('/receipts/%2E%2E%2Fetc%2Fpasswd');
		// Whatever the SPA does with the decoded path (not-found state or the
		// 404 page), it must render a heading and not crash to a blank page.
		await expect(page.locator('h1').first()).toBeVisible({ timeout: 10_000 });
		await expect(page).not.toHaveURL(/\/login/);
	});

	test('tampered session cookie bounces to login', async ({ page, context }) => {
		await registerUser(context, 'e2e-xss');
		await page.goto('/');
		await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

		const cookies = await context.cookies();
		const session = cookies.find((c) => c.name === 'vb_session');
		expect(session).toBeTruthy();
		// Flip the last hex char of the HMAC -> signature mismatch -> 401.
		const value = session!.value;
		const tampered = value.slice(0, -1) + (value.endsWith('0') ? '1' : '0');
		await context.addCookies([{ ...session!, value: tampered }]);

		await page.goto('/receipts');
		await expect(page).toHaveURL(/\/login$/);
	});
});
