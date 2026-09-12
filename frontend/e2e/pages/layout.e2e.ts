import { expect, test } from '@playwright/test';
import { registerUser } from '../helpers/auth';

test.describe('app chrome', () => {
	test('theme toggle persists', async ({ page, context }) => {
		await registerUser(context, 'e2e-layout');
		await page.goto('/');
		await page.getByRole('button', { name: 'Toggle theme' }).click();
		expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
		await page.reload();
		expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
	});

	test('mobile navigation works at 375px', async ({ page, context }) => {
		await registerUser(context, 'e2e-layout');
		await page.setViewportSize({ width: 375, height: 812 });
		await page.goto('/');

		// Bottom nav is visible, sidebar is hidden at this width.
		await expect(page.getByRole('link', { name: 'Search' })).toBeVisible();
		await page.getByRole('button', { name: 'More' }).click();
		await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible();
		await expect(page.getByRole('menuitem', { name: 'Toggle theme' })).toBeVisible();

		await page.getByRole('menuitem', { name: 'Sign out' }).click();
		await expect(page).toHaveURL(/\/login$/);
	});
});
