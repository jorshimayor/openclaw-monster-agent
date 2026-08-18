// Playwright config stub — edit and rename to playwright.config.ts when ready.
//
// Setup steps to actually run the E2E specs:
//
//   1. Install Playwright:
//        npm i -D @playwright/test @types/node
//
//   2. Install browsers (Chromium is enough for smoke):
//        npx playwright install chromium
//
//   3. Rename this file:
//        mv e2e/playwright.config.stub.ts e2e/playwright.config.ts
//
//   4. Make sure the frontend dev server is running on http://localhost:3000
//        (or update webServer.command / baseURL below to match).
//
//   5. Run specs:
//        npx playwright test --config=e2e/playwright.config.ts
//
// -----------------------------------------------------------------------------
// Example real config (uncomment once deps are installed):
//
// import { defineConfig, devices } from '@playwright/test';
//
// export default defineConfig({
//   testDir: './.',
//   testMatch: '**/*.spec.ts',
//   fullyParallel: true,
//   forbidOnly: !!process.env.CI,
//   retries: process.env.CI ? 2 : 0,
//   workers: process.env.CI ? 1 : undefined,
//   reporter: [
//     ['list'],
//     ['html', { open: 'never', outputFolder: '../playwright-report' }],
//   ],
//   outputDir: '../test-results/e2e',
//   use: {
//     baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
//     trace: 'on-first-retry',
//     screenshot: 'only-on-failure',
//   },
//   projects: [
//     {
//       name: 'chromium',
//       use: { ...devices['Desktop Chrome'] },
//     },
//     // Optional: add Firefox and WebKit projects below
//     // { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
//     // { name: 'webkit',  use: { ...devices['Desktop Safari']  } },
//   ],
//   /* Run the frontend dev server before starting the tests */
//   // webServer: {
//   //   command: 'npm run dev',
//   //   url: 'http://localhost:3000',
//   //   reuseExistingServer: !process.env.CI,
//   //   stdout: 'pipe',
//   //   stderr: 'pipe',
//   // },
// });
