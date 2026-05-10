import { test, expect } from '@playwright/test'

/**
 * W0 skeleton for the mutation-policy contract test.
 *
 * The dashboard is read-only. Workstream D wires the full implementation:
 * intercept every fetch from the SPA, then fail the test if any non-GET
 * request hits /apis/default/. Whitelist by URL match:
 *   - /oauth2/default/token (POST)  — token exchange
 *   - revocation_endpoint  (POST)   — only if OIDC config advertises one
 *
 * The plant-and-revert dry-run lives at
 * dashboard-modern/agentdocs/regression-dryrun/ (created in W-D).
 */
test.describe('Mutation contract', () => {
  test('SPA never sends non-GET to /apis/default/ (W-D fills in)', async ({ page }) => {
    const offending: Array<string> = []
    await page.route('**/apis/default/**', async (route) => {
      const req = route.request()
      if (req.method() !== 'GET') {
        offending.push(`${req.method()} ${req.url()}`)
      }
      await route.continue()
    })

    await page.goto('/dashboard')
    // Workstream D: drive the SPA harder here (load all 6 cards, etc.)
    expect(offending, 'no non-GET requests to /apis/default/').toEqual([])
  })
})
