/**
 * One-shot fetch + cache of /oauth2/default/.well-known/openid-configuration.
 *
 * NOTE: separate from SMART discovery. SMART configuration lives at
 *   ${VITE_OPENEMR_FHIR_BASE_URL}/.well-known/smart-configuration
 * and is auto-discovered by fhirclient. OIDC discovery lives at
 *   ${VITE_OPENEMR_BASE_URL}/oauth2/default/.well-known/openid-configuration
 * and is what we read here for token + logout + (optional) revocation endpoints.
 *
 * Verified 2026-05-10: OpenEMR does NOT advertise revocation_endpoint.
 * getRevocationEndpoint() will return null for this deployment.
 */

export type OidcConfig = Readonly<{
  issuer: string
  authorization_endpoint: string
  token_endpoint: string
  end_session_endpoint: string | null
  revocation_endpoint: string | null
  introspection_endpoint: string | null
  [extra: string]: unknown
}>

let cached: OidcConfig | null = null

export async function getOidcConfig(): Promise<OidcConfig> {
  if (cached !== null) return cached

  const baseUrl = import.meta.env.VITE_OPENEMR_BASE_URL as string
  const url = `${baseUrl}/oauth2/default/.well-known/openid-configuration`

  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`OIDC discovery failed: ${response.status} ${response.statusText}`)
  }

  const raw = (await response.json()) as Record<string, unknown>

  cached = {
    issuer: (raw['issuer'] as string) ?? '',
    authorization_endpoint: (raw['authorization_endpoint'] as string) ?? '',
    token_endpoint: (raw['token_endpoint'] as string) ?? '',
    end_session_endpoint: (raw['end_session_endpoint'] as string | null | undefined) ?? null,
    revocation_endpoint: (raw['revocation_endpoint'] as string | null | undefined) ?? null,
    introspection_endpoint: (raw['introspection_endpoint'] as string | null | undefined) ?? null,
    ...raw,
  }

  return cached
}

export async function getEndSessionEndpoint(): Promise<string | null> {
  const cfg = await getOidcConfig()
  return cfg.end_session_endpoint
}

export async function getRevocationEndpoint(): Promise<string | null> {
  const cfg = await getOidcConfig()
  return cfg.revocation_endpoint
}

export async function getTokenEndpoint(): Promise<string> {
  const cfg = await getOidcConfig()
  if (!cfg.token_endpoint) {
    throw new Error('OIDC config missing token_endpoint')
  }
  return cfg.token_endpoint
}

/** Reset the cache — used in tests only. */
export function _resetOidcCache(): void {
  cached = null
}
