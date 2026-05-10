/**
 * SMART/OAuth wiring. Workstream A implements; W0 only locks the surface.
 *
 * Defaults pulled from Vite env at build time. The .env.example documents
 * the expected variables.
 */

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
    redirectUri: '/index.html',
    iss: import.meta.env.VITE_OPENEMR_FHIR_BASE_URL ?? '',
    pkceMode: 'ifSupported',
  }
}

/**
 * Workstream A: kick off the SMART authorize redirect with FHIR.oauth2.authorize().
 */
export async function authorize(): Promise<void> {
  throw new Error('authorize(): not implemented — Workstream A')
}

/**
 * Workstream A: complete the OAuth code exchange via FHIR.oauth2.ready()
 * and return the bound Client.
 */
export async function ready(): Promise<unknown> {
  throw new Error('ready(): not implemented — Workstream A')
}
