import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the EVIDENCE CAPTURE script only.
 *
 * This is deliberately NOT `playwright.config.ts`. The automated suite
 * (`playwright.config.ts`, `testDir: ./e2e`) must never see
 * `cdp-automated.spec.ts`: that script needs a live backend, writes
 * artifact bundles to disk, and bundles five assertions into one test.
 * See the docblock at the top of the spec for the full reasoning.
 *
 * Run:
 *   pnpm exec playwright test --config=e2e-evidence/playwright.evidence.config.ts
 *
 * It boots the same Vite dev server on :5173, and it will fail at the
 * login step unless a real API is reachable and the credentials in the
 * spec's step 2 are replaced with a real account.
 */
export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  // No retries: a capture bundle is only useful if it reflects the
  // first attempt. A retry would write a second timestamped directory
  // and the operator would have to guess which one is the real run.
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
