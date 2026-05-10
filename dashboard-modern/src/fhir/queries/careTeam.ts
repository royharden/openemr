import type { CareTeamDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Fetches CareTeam?patient={patientId}.
 *
 * Status filtering happens in the adapter (status === 'active').
 *
 * Practitioner expansion default: per-participant follow-up reads with
 * a parallelism cap of 3. `_include=CareTeam:participant` is enabled
 * ONLY if the W0 live probe (FHIR_QUERY_PROBES.md) confirms OpenEMR
 * honors it AND AgDR-0086 is filed. Otherwise stick to the default.
 */
export async function getActiveCareTeam(
  _patientId: string,
): Promise<ReadonlyArray<CareTeamDisplay>> {
  throw new Error('getActiveCareTeam(): not implemented — Workstream C')
}
