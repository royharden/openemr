import type { MedicationRequest } from '@/fhir/schemas/medicationRequest'
import type { MedicationDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Per Phase 0 spike outcome (MEDICATION_PARITY_SPIKE.md):
 *   - FHIR-only path: filter MedicationRequest to lists-row entries
 *     using the discovered discriminator (category/intent/meta.source).
 *   - REST fallback: this adapter consumes a Standard REST shape
 *     (still typed via a Zod schema in W-B) — see AgDR-0085.
 *
 * Status filtering (active only) happens here.
 */
export function adaptMedications(
  _resources: ReadonlyArray<MedicationRequest>,
): ReadonlyArray<MedicationDisplay> {
  throw new Error('adaptMedications(): not implemented — Workstream B')
}
