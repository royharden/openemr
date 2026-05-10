import { http, HttpResponse } from 'msw'

/**
 * W0 stub MSW handlers. Workstreams A/B/C extend with their resource-
 * specific responses; W0 lands a smoke handler so MSW boots cleanly.
 *
 * When extending: add per-resource handlers that read JSON fixtures
 * from src/test/fixtures/*.json. Workstream A owns the auth-side
 * handlers (smart-configuration discovery, openid-configuration,
 * /oauth2/default/token, optional revocation).
 */
export const handlers = [
  // Smoke handler so the MSW server has at least one route at W0.
  http.get('/__msw_smoke', () => HttpResponse.json({ ok: true })),
]
