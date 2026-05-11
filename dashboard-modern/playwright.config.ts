import { defineConfig, devices } from '@playwright/test'

// In Playwright E2E tests, we run the SPA without the MSW browser service
// worker (VITE_USE_MSW=0) because headless Chromium's service worker
// lifecycle can delay or prevent lazy-chunk resolution in the Vite dev server.
// The W0 card stubs render headings + skeletons without making any FHIR
// calls, so MSW is not needed for the smoke or contract tests to pass.
// Live-mode tests (VITE_USE_MSW=0) also need no MSW.
//
// To run with MSW browser worker enabled, set PW_USE_MSW=1 explicitly.
const PW_USE_MSW = process.env.PW_USE_MSW === '1'
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './tests',
  testIgnore: ['**/unit/**'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    // Required for live-mode tests that hit OpenEMR's self-signed cert.
    // Harmless in mock-mode (MSW intercepts before TLS).
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Firefox is opt-in: set PW_BROWSERS=firefox to include it.
    ...(process.env.PW_BROWSERS?.includes('firefox')
      ? [
          {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
          },
        ]
      : []),
  ],
  webServer: {
    command: PW_USE_MSW ? 'npm run start:mock' : 'npm run start:live',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // Default off for Playwright: service worker delays can prevent
      // lazy chunk resolution in headless Chromium.
      VITE_USE_MSW: PW_USE_MSW ? '1' : '0',
    },
  },
})
