import { expect, test } from '@playwright/test';
import { registerUser, uniqueUsername } from './helpers/auth';
import { loadFixture } from './helpers/fixtures';
import { setStubMode, stubGuard } from './helpers/stub';
import { uploadFixture } from './helpers/ui';

// Verifies the helper library end-to-end. Deleted in the first-run task
// (superseded by flows/first-run.e2e.ts).
test.describe('helpers smoke', () => {
	stubGuard();

	test('auth, fixtures, stub mode and the upload composite all work', async ({ page, context }) => {
		test.setTimeout(120_000);
		const creds = await registerUser(context, 'e2e-smoke');
		expect(creds.username).toMatch(/^e2e-smoke-/);
		expect(uniqueUsername('x')).toMatch(/^x-/);

		await setStubMode('broken');
		await setStubMode('ok');

		const fixture = await loadFixture('a');
		expect(fixture.expected.merchant_name).toBe('Aldi Test');
		expect(fixture.bytes.length).toBeGreaterThan(0);

		const receiptId = await uploadFixture(page, context, fixture);
		expect(receiptId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
		await expect(page.getByText('Verified', { exact: true })).toBeVisible();
	});
});
