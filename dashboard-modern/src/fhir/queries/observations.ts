import type { LabResultDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Fetches Observation?patient={patientId}&category=laboratory.
 * `category` is fundamental and OK to keep server-side.
 *
 * `_count` and `_sort=-effectiveDateTime` may be honored — verify in
 * Workstream C's pre-spike. If silently ignored, sort + limit in adapter.
 *
 * Returns the most recent {n} laboratory observations for the patient.
 */
export async function getRecentLabResults(
  _patientId: string,
  _n: number = 10,
): Promise<ReadonlyArray<LabResultDisplay>> {
  throw new Error('getRecentLabResults(): not implemented — Workstream C')
}
