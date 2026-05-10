import { test, expect } from '@playwright/test'

/**
 * W0 skeleton — Workstreams A and D fill this in.
 *
 * A: SMART launch happy path → /dashboard reachable.
 * D: 6 cards render (mock mode, MSW handlers serve fixtures).
 * D: live-mode test gated behind VITE_USE_MSW=0 env flag.
 */
test.describe('Modern Patient Dashboard — smoke', () => {
  test('home page mounts the SPA shell', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/dashboard$/)
    // The W0 stub renders skeletons, not real content. Verify the
    // application actually mounted by checking for a loading indicator.
    await expect(page.locator('[aria-busy="true"]').first()).toBeVisible()
  })
})
