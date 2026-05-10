import type { MedicationRequest } from '@/fhir/schemas/medicationRequest'
import type { PrescriptionDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Filters MedicationRequest to formal prescription entries (per Phase 0
 * discriminator). Status filtering (active) happens here. Resolves
 * `requester.reference` → Practitioner name via a bounded follow-up
 * read in the query layer.
 *
 * NOTE: practitioner-name resolution is async; the query function
 * passes already-resolved names to this adapter. This signature stays
 * synchronous to keep the adapter pure-function-testable.
 */
export function adaptPrescriptions(
  _resources: ReadonlyArray<MedicationRequest>,
  _practitionerNamesById: ReadonlyMap<string, string>,
): ReadonlyArray<PrescriptionDisplay> {
  throw new Error('adaptPrescriptions(): not implemented — Workstream C')
}
