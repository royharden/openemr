/**
 * Typed session shape. Notably does NOT carry the bearer token —
 * fhirclient owns sessionStorage; the SPA reads only what's safe to
 * surface in dev panels.
 */

export type Session = Readonly<{
  userId: string | null
  patientContext: string | null // patient FHIR id
  expiresAt: number | null // epoch ms
}>

export const EMPTY_SESSION: Session = {
  userId: null,
  patientContext: null,
  expiresAt: null,
}

/**
 * Workstream A implements the body — derives Session from the
 * fhirclient state without exposing the access token.
 */
export async function getSession(): Promise<Session> {
  throw new Error('getSession(): not implemented — Workstream A')
}
