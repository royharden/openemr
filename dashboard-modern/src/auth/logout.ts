/**
 * Discovery-driven logout. NEVER hard-codes /oauth2/default/logout.
 *
 * Flow (master plan §7, AgDR-0088):
 * 1. Fetch OIDC config to find endpoints.
 * 2. If revocation_endpoint is advertised (not the case for this OpenEMR
 *    deployment — confirmed in status §M), revoke access + refresh tokens.
 *    The guard on cfg.revocation_endpoint ensures we never POST to a
 *    non-existent endpoint.
 * 3. Clear sessionStorage (removes fhirclient's token state).
 * 4. Redirect to end_session_endpoint (RP-Initiated Logout) if available,
 *    otherwise fall back to the app root.
 */

import { getOidcConfig } from '@/auth/oidcConfig'
import { getSmartConfig } from '@/auth/smartClient'

export type LogoutOptions = Readonly<{
  postLogoutRedirectUri?: string
}>

export async function logout(options?: LogoutOptions): Promise<void> {
  const cfg = await getOidcConfig()
  const { clientId } = getSmartConfig()
  const postLogoutUri = options?.postLogoutRedirectUri ?? `${window.location.origin}/`

  // Step 1 (conditional): revoke tokens at revocation_endpoint if advertised.
  // OpenEMR does NOT advertise this endpoint (status companion §M), so this
  // block is skipped in practice — but the code handles future deployments.
  if (cfg.revocation_endpoint != null) {
    const revokeToken = async (token: string, hint: string) => {
      try {
        await fetch(cfg.revocation_endpoint as string, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            token,
            token_type_hint: hint,
            client_id: clientId,
          }),
        })
      } catch {
        // Revocation failure is non-fatal — we still clear local state.
      }
    }

    // Pull tokens from sessionStorage before clearing it.
    const rawState = sessionStorage.getItem('SMART_KEY')
    if (rawState != null) {
      try {
        const stateKey = JSON.parse(rawState) as string
        const stateRaw = sessionStorage.getItem(stateKey)
        if (stateRaw != null) {
          const state = JSON.parse(stateRaw) as {
            tokenResponse?: { access_token?: string; refresh_token?: string }
          }
          const tokenResp = state.tokenResponse
          const tasks: Promise<void>[] = []
          if (tokenResp?.access_token) {
            tasks.push(revokeToken(tokenResp.access_token, 'access_token'))
          }
          if (tokenResp?.refresh_token) {
            tasks.push(revokeToken(tokenResp.refresh_token, 'refresh_token'))
          }
          await Promise.allSettled(tasks)
        }
      } catch {
        // Parsing failure: skip revocation, still clear storage.
      }
    }
  }

  // Step 2: clear all fhirclient session storage.
  sessionStorage.clear()

  // Step 3: redirect to end_session_endpoint (RP-Initiated Logout) or root.
  if (cfg.end_session_endpoint != null) {
    const url = new URL(cfg.end_session_endpoint)
    url.searchParams.set('post_logout_redirect_uri', postLogoutUri)
    window.location.href = url.toString()
  } else {
    window.location.href = postLogoutUri
  }
}
