/**
 * One-shot fetch + cache of /oauth2/default/.well-known/openid-configuration.
 * Workstream A implements. W0 locks the surface.
 *
 * NOTE: separate from SMART discovery. SMART configuration lives at
 *   ${VITE_OPENEMR_FHIR_BASE_URL}/.well-known/smart-configuration
 * and is auto-discovered by fhirclient. OIDC discovery lives at
 *   ${VITE_OPENEMR_BASE_URL}/oauth2/default/.well-known/openid-configuration
 * and is what we read here for token + logout + (optional) revocation
 * endpoints.
 */

export type OidcConfig = Readonly<{
  issuer: string
  authorization_endpoint: string
  token_endpoint: string
  end_session_endpoint: string | null
  revocation_endpoint: string | null
  introspection_endpoint: string | null
  // Pass-through of anything else the OIDC server advertises.
  [extra: string]: unknown
}>

export async function getOidcConfig(): Promise<OidcConfig> {
  throw new Error('getOidcConfig(): not implemented — Workstream A')
}

export async function getEndSessionEndpoint(): Promise<string | null> {
  throw new Error('getEndSessionEndpoint(): not implemented — Workstream A')
}

export async function getRevocationEndpoint(): Promise<string | null> {
  throw new Error('getRevocationEndpoint(): not implemented — Workstream A')
}

export async function getTokenEndpoint(): Promise<string> {
  throw new Error('getTokenEndpoint(): not implemented — Workstream A')
}
