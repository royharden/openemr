/**
 * Typed session shape. Notably does NOT carry the bearer token —
 * fhirclient owns sessionStorage; the SPA reads only what's safe to
 * surface in dev panels or the showSession=1 overlay.
 */

import { ready } from '@/auth/smartClient'

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
 * Derives a safe Session from the fhirclient state without exposing
 * the access token. Calls fhirclient.ready() to get the bound Client,
 * then reads userId, patient context, and token expiry.
 *
 * expiresAt: fhirclient stores `expiresAt` as Unix seconds in its
 * ClientState, so multiply by 1000 to get epoch ms.
 */
export async function getSession(): Promise<Session> {
  const client = await ready()

  const userId = client.getUserId() ?? null
  const patientContext = client.getPatientId() ?? null

  // fhirclient stores expiresAt as Unix epoch seconds
  const expiresAtSec = client.getState('expiresAt') as number | undefined | null
  const expiresAt = expiresAtSec != null ? expiresAtSec * 1000 : null

  return { userId, patientContext, expiresAt }
}
