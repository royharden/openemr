/**
 * Workstream A — auth unit tests.
 *
 * Covers:
 * 1. oidcConfig — happy path fetch + cache + endpoint getters
 * 2. oidcConfig — revocation_endpoint absent (matches live OpenEMR)
 * 3. session.getSession — derives safe view without token
 * 4. logout — clears sessionStorage + redirects to end_session_endpoint
 * 5. logout — graceful degradation when revocation_endpoint is absent
 * 6. logout — issues revocation POST when endpoint IS advertised
 *
 * fhirclient FHIR.oauth2.ready() is mocked at module level so no real
 * OAuth flow is required. MSW intercepts the OIDC discovery fetch.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { _resetOidcCache, getOidcConfig, getEndSessionEndpoint, getRevocationEndpoint, getTokenEndpoint } from '@/auth/oidcConfig'
import { OIDC_CONFIG_RESPONSE_WITH_REVOCATION } from '../fixtures/oidcFixtures'

// ─── fhirclient mock ──────────────────────────────────────────────────────────

const mockClient = {
  getUserId: vi.fn<() => string | null>(() => 'user-practitioner-1'),
  getPatientId: vi.fn<() => string | null>(() => 'test-patient-uuid-9001'),
  getState: vi.fn<(path?: string) => unknown>((path?: string) => {
    if (path === 'expiresAt') return 1800000000 // epoch seconds
    return undefined
  }),
  request: vi.fn<() => Promise<unknown>>(),
}

vi.mock('fhirclient', () => ({
  default: {
    oauth2: {
      authorize: vi.fn().mockResolvedValue(undefined),
      ready: vi.fn().mockResolvedValue(mockClient),
    },
  },
}))

// ─── location.href mock helper ────────────────────────────────────────────────

function mockLocationHref() {
  const hrefSetter = vi.fn<(v: string) => void>()
  const original = window.location
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: new Proxy(original, {
      set(target, prop, value) {
        if (prop === 'href') { hrefSetter(value as string); return true }
        return Reflect.set(target, prop, value)
      },
    }),
  })
  return {
    hrefSetter,
    restore() {
      Object.defineProperty(window, 'location', { configurable: true, value: original })
    },
  }
}

// ─── oidcConfig ───────────────────────────────────────────────────────────────

describe('oidcConfig', () => {
  beforeEach(() => { _resetOidcCache() })
  afterEach(() => { _resetOidcCache() })

  it('fetches and returns OIDC config on first call', async () => {
    const cfg = await getOidcConfig()
    expect(cfg.issuer).toBe('https://localhost:9300/oauth2/default')
    expect(cfg.token_endpoint).toBe('https://localhost:9300/oauth2/default/token')
    expect(cfg.end_session_endpoint).toBe('https://localhost:9300/oauth2/default/logout')
  })

  it('returns cached config on subsequent calls (same object reference)', async () => {
    const cfg1 = await getOidcConfig()
    const cfg2 = await getOidcConfig()
    expect(cfg1).toBe(cfg2)
  })

  it('getEndSessionEndpoint() returns the logout URL', async () => {
    expect(await getEndSessionEndpoint()).toBe('https://localhost:9300/oauth2/default/logout')
  })

  it('getRevocationEndpoint() returns null — not advertised by this OpenEMR', async () => {
    expect(await getRevocationEndpoint()).toBeNull()
  })

  it('getTokenEndpoint() returns the token URL', async () => {
    expect(await getTokenEndpoint()).toBe('https://localhost:9300/oauth2/default/token')
  })
})

// ─── session.getSession ───────────────────────────────────────────────────────

describe('getSession', () => {
  it('derives safe Session without exposing access token', async () => {
    const { getSession } = await import('@/auth/session')
    const session = await getSession()
    expect(session.userId).toBe('user-practitioner-1')
    expect(session.patientContext).toBe('test-patient-uuid-9001')
    expect(session.expiresAt).toBe(1800000000 * 1000)
    expect(Object.keys(session)).not.toContain('access_token')
    expect(Object.keys(session)).not.toContain('refresh_token')
    expect(Object.keys(session)).not.toContain('id_token')
  })

  it('returns null fields when client has no patient context (expired/missing session)', async () => {
    const FHIR = (await import('fhirclient')).default
    vi.mocked(FHIR.oauth2.ready).mockResolvedValueOnce({
      getUserId: () => null,
      getPatientId: () => null,
      getState: () => null,
      request: vi.fn(),
    } as never)

    const { getSession } = await import('@/auth/session')
    const session = await getSession()
    expect(session.userId).toBeNull()
    expect(session.patientContext).toBeNull()
    expect(session.expiresAt).toBeNull()
  })
})

// ─── logout ───────────────────────────────────────────────────────────────────

describe('logout', () => {
  beforeEach(() => {
    _resetOidcCache()
    sessionStorage.clear()
  })

  afterEach(() => {
    _resetOidcCache()
    sessionStorage.clear()
  })

  it('clears sessionStorage and redirects to end_session_endpoint', async () => {
    sessionStorage.setItem('SMART_KEY', JSON.stringify('test-state-key'))
    sessionStorage.setItem('test-state-key', JSON.stringify({ tokenResponse: { access_token: 'tok' } }))
    sessionStorage.setItem('other', 'value')

    const { hrefSetter, restore } = mockLocationHref()
    try {
      const { logout } = await import('@/auth/logout')
      await logout()

      expect(sessionStorage.length).toBe(0)
      expect(hrefSetter).toHaveBeenCalledOnce()
      const redirectUrl = hrefSetter.mock.calls[0]?.[0] as string
      expect(redirectUrl).toContain('https://localhost:9300/oauth2/default/logout')
      expect(redirectUrl).toContain('post_logout_redirect_uri=')
    } finally {
      restore()
    }
  })

  it('uses custom postLogoutRedirectUri when provided', async () => {
    const { hrefSetter, restore } = mockLocationHref()
    try {
      const { logout } = await import('@/auth/logout')
      await logout({ postLogoutRedirectUri: 'http://localhost:5173/goodbye' })

      const redirectUrl = hrefSetter.mock.calls[0]?.[0] as string
      expect(redirectUrl).toContain(encodeURIComponent('http://localhost:5173/goodbye'))
    } finally {
      restore()
    }
  })

  it('skips revocation POST when revocation_endpoint is absent (live OpenEMR behavior)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const { hrefSetter, restore } = mockLocationHref()
    try {
      const { logout } = await import('@/auth/logout')
      await logout()

      const revocationCalls = fetchSpy.mock.calls.filter(
        ([input]) => typeof input === 'string' && (input as string).includes('/revoke'),
      )
      expect(revocationCalls).toHaveLength(0)
      expect(hrefSetter).toHaveBeenCalledOnce()
    } finally {
      fetchSpy.mockRestore()
      restore()
    }
  })

  it('issues revocation POST when revocation_endpoint IS advertised', async () => {
    const { server } = await import('@/test/msw/server')
    const { http, HttpResponse } = await import('msw')

    server.use(
      http.get('*/oauth2/default/.well-known/openid-configuration', () =>
        HttpResponse.json(OIDC_CONFIG_RESPONSE_WITH_REVOCATION),
      ),
    )

    const stateKey = 'test-revoke-state'
    sessionStorage.setItem('SMART_KEY', JSON.stringify(stateKey))
    sessionStorage.setItem(stateKey, JSON.stringify({
      tokenResponse: { access_token: 'tok-to-revoke', refresh_token: 'rtok-to-revoke' },
    }))

    // MSW intercepts the revocation POST — just confirm it's called.
    server.use(
      http.post('*/oauth2/default/revoke', () => HttpResponse.json({ ok: true })),
    )

    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const { restore } = mockLocationHref()
    try {
      const { logout } = await import('@/auth/logout')
      await logout()

      // fetch was called for OIDC discovery + at least one revocation POST
      const revocationCalls = fetchSpy.mock.calls.filter(
        ([input]) => typeof input === 'string' && (input as string).includes('/revoke'),
      )
      expect(revocationCalls.length).toBeGreaterThanOrEqual(1)
      expect(sessionStorage.length).toBe(0)
    } finally {
      fetchSpy.mockRestore()
      restore()
    }
  })
})
