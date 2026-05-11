import { test, expect } from '@playwright/test'

/**
 * Mutation-policy contract test — load-bearing gate (AgDR-0084).
 *
 * The SPA is strictly read-only. Any non-GET request to /apis/default/ is a
 * policy violation and MUST fail this test. Token + revocation endpoint POSTs
 * are whitelisted by URL because they are OAuth protocol operations, not FHIR
 * mutations.
 *
 * Whitelist is discovered at test setup from the OIDC config so it
 * automatically expands if OpenEMR ever starts advertising revocation_endpoint.
 * As of 2026-05-10 this OpenEMR does NOT advertise revocation_endpoint (status
 * companion §M), so the whitelist is exactly: [/oauth2/default/token].
 */

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'
const OPENEMR_BASE = process.env.VITE_OPENEMR_BASE_URL ?? 'https://localhost:9300'
const OIDC_CONFIG_URL = `${OPENEMR_BASE}/oauth2/default/.well-known/openid-configuration`

/** URLs that are permitted to use POST (OAuth protocol — not FHIR mutations). */
async function buildMutationWhitelist(): Promise<Set<string>> {
  const whitelist = new Set<string>()

  try {
    // Attempt live OIDC discovery. In mock mode this will fail (MSW doesn't
    // serve the OIDC config URL in the browser worker by default), so we
    // fall back to the known-good value from status companion §M.
    const resp = await fetch(OIDC_CONFIG_URL, {
      // node-fetch in Playwright context; cast to RequestInit
      signal: AbortSignal.timeout(5_000),
    } as RequestInit)
    if (resp.ok) {
      const cfg = (await resp.json()) as Record<string, unknown>
      if (typeof cfg['token_endpoint'] === 'string') {
        whitelist.add(cfg['token_endpoint'])
      }
      // Only add revocation_endpoint if it is advertised (not the case on this
      // OpenEMR, but handle gracefully for future deployments).
      if (typeof cfg['revocation_endpoint'] === 'string') {
        whitelist.add(cfg['revocation_endpoint'])
      }
    }
  } catch {
    // Discovery unavailable (expected in mock mode). Use the known value.
  }

  // Fallback: always allow the known token endpoint regardless of discovery.
  whitelist.add(`${OPENEMR_BASE}/oauth2/default/token`)

  return whitelist
}

test.describe('Mutation contract — read-only policy (AgDR-0084)', () => {
  let whitelist: Set<string>

  test.beforeAll(async () => {
    whitelist = await buildMutationWhitelist()
  })

  test('SPA never sends non-GET to /apis/default/', async ({ page }) => {
    const violations: string[] = []

    // Intercept every network request made by the page.
    page.on('request', (req) => {
      const url = req.url()
      const method = req.method()

      // Only care about /apis/default/ traffic.
      if (!url.includes('/apis/default/')) return

      // GET is always allowed.
      if (method === 'GET') return

      // Whitelisted OAuth endpoints are allowed (POST only).
      if (whitelist.has(url)) return

      violations.push(`${method} ${url}`)
    })

    await page.goto(`${BASE_URL}/dashboard`)
    await page.waitForSelector('#root', { timeout: 10_000 })

    // Drive the SPA: wait for all sections to be present (either data or skeletons).
    // This ensures any async fetches triggered by card mounts have fired.
    await page.waitForTimeout(2_000)

    expect(
      violations,
      `No non-GET requests to /apis/default/ are allowed.\nViolations:\n${violations.join('\n')}`,
    ).toEqual([])
  })

  test('whitelist covers the known token endpoint', () => {
    expect(whitelist.size).toBeGreaterThanOrEqual(1)
    // The token endpoint must always be whitelisted.
    const hasToken = [...whitelist].some((url) => url.includes('/oauth2/default/token'))
    expect(hasToken, 'token endpoint should be in whitelist').toBe(true)
  })
})
