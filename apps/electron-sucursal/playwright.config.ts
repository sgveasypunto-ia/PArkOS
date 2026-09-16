import { defineConfig } from '@playwright/test';

/**
 * Playwright config — boots the built Electron app via `_electron`
 * and runs the scaffold smoke + axe-core WCAG 2.1 AA checks.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  timeout: 60_000,
});
