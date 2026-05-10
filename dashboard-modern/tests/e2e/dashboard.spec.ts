import { test, expect } from '@playwright/test'

/**
 * Dashboard smoke tests.
 *
 * Playwright runs with VITE_USE_MSW=0 (no browser service worker) by default
 * so that Vite's lazy chunk resolution is not delayed by service worker
 * lifecycle events in headless Chromium.
 *
 * In the W0+B+C stub state, navigating to /dashboard without a valid SMART
 * session triggers an auth error in the card query hooks (no 'state' param).
 * The ErrorBoundary wraps each section, so the SPA renders gracefully rather
 * than crashing. The smoke test verifies this graceful rendering and the
 * overall layout structure. Full data-path testing belongs in SMART E2E tests
 * (Team A) and component-level tests (Teams B/C).
 *
 * All synthetic data. No PHI. Demo patient is Maria G. (pid 9001).
 */

test.describe('Modern Patient Dashboard — smoke', () => {
  test('SPA shell mounts and redirects to /dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10_000 })
  })

  test('SPA renders main content area (dashboard or auth error state)', async ({ page }) => {
    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })

    // The SPA must render a <main> element — either the dashboard grid or an
    // auth-error state. Both are valid for this smoke (full SMART auth is
    // tested in Team A's spec).
    await expect(page.locator('main')).toBeVisible({ timeout: 12_000 })
  })

  test('no uncaught JS errors on mount', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))

    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 12_000 })

    expect(errors, 'no uncaught JS errors on initial mount').toEqual([])
  })

  test('6 section headings visible when SMART session is active', async ({ page }) => {
    // This test is skipped unless PW_WITH_SMART_SESSION=1 is set (live-mode
    // SMART auth provided externally — e.g. by seeding sessionStorage before
    // page load). Without a session the cards render an auth-error state.
    test.skip(
      process.env.PW_WITH_SMART_SESSION !== '1',
      'Requires active SMART session (set PW_WITH_SMART_SESSION=1)',
    )

    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 12_000 })

    const expectedSections = [
      'Allergies',
      'Problem List',
      'Medications',
      'Prescriptions',
      'Care Team',
      'Lab Results',
    ]

    for (const section of expectedSections) {
      await expect(
        page.getByRole('heading', { name: section }),
        `"${section}" section heading should be visible`,
      ).toBeVisible({ timeout: 8_000 })
    }
  })
})

test.describe('Modern Patient Dashboard — mock-mode MSW stub smoke', () => {
  // These tests run in MSW browser mode (PW_USE_MSW=1) where service worker
  // intercepts FHIR calls and serves fixtures. Without a real SMART session,
  // the MSW handlers must also mock the auth/session layer for cards to render.
  test.skip(
    process.env.PW_USE_MSW !== '1',
    'MSW browser mode only — set PW_USE_MSW=1',
  )

  test('all 6 section card headings visible with MSW fixtures', async ({ page }) => {
    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 15_000 })

    const expectedSections = [
      'Allergies',
      'Problem List',
      'Medications',
      'Prescriptions',
      'Care Team',
      'Lab Results',
    ]

    for (const section of expectedSections) {
      await expect(
        page.getByRole('heading', { name: section }),
        `"${section}" section heading should be visible`,
      ).toBeVisible({ timeout: 8_000 })
    }
  })
})
