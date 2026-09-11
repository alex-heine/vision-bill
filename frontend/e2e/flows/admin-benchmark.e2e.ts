import { expect, test } from '@playwright/test';
import { loginAdmin } from '../helpers/auth';
import { loadFixture } from '../helpers/fixtures';
import { stubGuard } from '../helpers/stub';
import { confirmDialog, uploadFixture } from '../helpers/ui';

test.describe('admin: benchmarks', () => {
	stubGuard();

	test('create a run and watch it complete in the results view', async ({ page, context }) => {
		test.setTimeout(180_000);
		await loginAdmin(context);
		const receiptId = await uploadFixture(page, context, await loadFixture('a'));

		await page.goto('/benchmarks');
		await expect(page.getByRole('checkbox', { name: 'e2e-vision' })).toBeChecked();
		await page.getByPlaceholder('Comma-separated receipt UUIDs').fill(receiptId);
		await page.getByRole('button', { name: 'Create benchmark' }).first().click();
		// The confirmation dialog is rendered inline (not role="dialog"),
		// so click the second "Create benchmark" button directly.
		await page.getByRole('button', { name: 'Create benchmark' }).nth(1).click();
		await expect(page).toHaveURL(/\/benchmarks\/results$/);

		// The run is picked up by the benchmark worker and finishes fast
		// (the stub answers instantly; ground truth = the verified receipt).
		await expect(page.getByText('Completed', { exact: true })).toBeVisible();
		await expect(page.getByText('1 / 1')).toBeVisible({ timeout: 60_000 });
		await expect(page.getByText('e2e-vision')).toBeVisible();
	});

	test('receipt used in a benchmark run cannot be deleted', async ({ page, context }) => {
		test.setTimeout(150_000);
		await loginAdmin(context);
		const receiptId = await uploadFixture(page, context, await loadFixture('b'));

		const run = await context.request.post('/api/v1/benchmarks', {
			data: { model_ids: ['e2e-vision'], receipt_ids: [receiptId] }
		});
		expect(run.status()).toBe(202);

		// Delete is triggered from the list page (not the detail page).
		// Scope the Remove button to the exact receipt via its link href.
		await page.goto('/receipts');
		await page
			.locator(`li:has(a[href$="/receipts/${receiptId}"])`)
			.getByRole('button', { name: 'Remove' })
			.click();
		await confirmDialog(page, 'Delete receipt?', 'Delete');
		await expect(
			page.getByText("This receipt is used in a benchmark run and can't be deleted.")
		).toBeVisible({ timeout: 15_000 });
		// Receipt must still be present (delete was blocked).
		await expect(page.locator(`a[href$="/receipts/${receiptId}"]`)).toBeVisible();
	});
});
