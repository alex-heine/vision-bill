import { defineConfig } from '@playwright/test';

// The E2E suite runs against an already-running vision-bill app (see
// `make docker-up` / `make run`). Point it at the host port the app is
// published on; it is not started here.
const baseURL = process.env.VB_E2E_BASE_URL ?? 'http://localhost:53625';

export default defineConfig({
	testDir: './src',
	testMatch: /.*\.e2e\.ts$/,
	timeout: 60_000,
	retries: 0,
	fullyParallel: false,
	reporter: [['list']],
	use: {
		baseURL,
		// Keep traces on failure to aid debugging of the live-app flow.
		trace: 'retain-on-failure'
	}
});
