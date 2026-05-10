import type { Observation } from '@/fhir/schemas/observation'
import type { LabResultDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Sorts Observations by effectiveDateTime descending and limits to {n}.
 * (Sort + limit happen here even when the server honors `_count` and
 * `_sort` — defensive default per the Workstream-0 status-filter
 * lesson.)
 *
 * Interpretation flag: from interpretation.coding[0].code (H/L/HH/LL/N).
 */
export function adaptLabs(
  _resources: ReadonlyArray<Observation>,
  _n: number,
): ReadonlyArray<LabResultDisplay> {
  throw new Error('adaptLabs(): not implemented — Workstream C')
}
