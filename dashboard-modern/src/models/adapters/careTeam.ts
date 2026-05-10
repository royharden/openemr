import type { CareTeam } from '@/fhir/schemas/careTeam'
import type { CareTeamDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Filters CareTeam to status === 'active' (CANONICAL — not server-side).
 *
 * Per-participant Practitioner names are resolved by the query layer
 * (per-participant follow-up reads) and threaded in here as a
 * pre-resolved map.
 */
export function adaptCareTeam(
  _resources: ReadonlyArray<CareTeam>,
  _practitionerNamesById: ReadonlyMap<string, string>,
): ReadonlyArray<CareTeamDisplay> {
  throw new Error('adaptCareTeam(): not implemented — Workstream C')
}
