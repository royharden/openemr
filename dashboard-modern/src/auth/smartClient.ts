/**
 * SMART/OAuth wiring via fhirclient v2.
 *
 * Key invariants (master plan §7, AgDR-0075):
 * - Public client only — no client_secret anywhere.
 * - SMART discovery is FHIR-side: fhirclient appends
 *   /.well-known/smart-configuration to the iss (FHIR base URL).
 * - PKCE is on by default (pkceMode: 'ifSupported').
 * - Token storage: fhirclient defaults to sessionStorage — never override.
 */

import FHIR from 'fhirclient'
import type Client from 'fhirclient/lib/Client'

export type SmartConfig = Readonly<{
  clientId: string
  scope: string
  redirectUri: string
  iss: string
  pkceMode: 'ifSupported' | 'required' | 'disabled'
}>

export function getSmartConfig(): SmartConfig {
  return {
    clientId: import.meta.env.VITE_SMART_CLIENT_ID ?? '',
    scope: import.meta.env.VITE_DEFAULT_SCOPES ?? '',
    redirectUri: `${window.location.origin}/index.html`,
    iss: import.meta.env.VITE_OPENEMR_FHIR_BASE_URL ?? '',
    pkceMode: 'ifSupported',
  }
}

/**
 * Kick off the SMART authorize redirect.
 * fhirclient reads `iss` and `launch` from the current URL automatically
 * for EHR-launch; for standalone-launch it uses the iss from config.
 */
export async function authorize(): Promise<void> {
  const cfg = getSmartConfig()
  await FHIR.oauth2.authorize({
    client_id: cfg.clientId,
    scope: cfg.scope,
    redirect_uri: cfg.redirectUri,
    iss: cfg.iss,
    pkceMode: cfg.pkceMode,
  })
}

/**
 * Complete the OAuth code exchange and return the bound Client instance.
 * Called from the /index.html callback page.
 */
export async function ready(): Promise<Client> {
  return FHIR.oauth2.ready()
}
