/**
 * Discovery-driven logout. NEVER hard-code /oauth2/default/logout.
 *
 * Workstream A implements. Status companion §M Verified-architectural-
 * assumptions table notes that OpenEMR does NOT advertise a
 * `revocation_endpoint`; the implementation must handle that gracefully
 * (revoke step skipped → still clear sessionStorage → still redirect to
 * `end_session_endpoint`).
 */

export type LogoutOptions = Readonly<{
  postLogoutRedirectUri?: string
}>

export async function logout(_options?: LogoutOptions): Promise<void> {
  throw new Error('logout(): not implemented — Workstream A')
}
