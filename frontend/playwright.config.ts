import { defineConfig } from '@playwright/test';

// The E2E suite runs against a real, self-started vision-bill stack
// (docker-compose.e2e.yml: app + postgres + deterministic LLM stub).
// Set VB_E2E_BASE_URL to point at an already-running stack instead.
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
		// The app is i18n (en/de); selectors use English strings, so pin the
		// locale to keep text-based locators deterministic on any host.
		locale: 'en-US',
		// Keep traces on failure to aid debugging of the live-app flow.
		trace: 'retain-on-failure'
	},
	webServer: {
		// Runs from rootDir (frontend/), so ../ = repo root. `-d` detaches; the
		// stack stays up after the run (stop it with `make e2e-down`).
		command: 'docker compose -f ../docker-compose.e2e.yml up -d --build',
		url: `${baseURL}/api/v1/system/ui-config`,
		reuseExistingServer: true,
		// First run builds the multi-stage app image (Node SPA + Python) — can
		// take several minutes; cached afterwards.
		timeout: 600_000
	}
});
