import type { MedicationDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Per Phase 0 medication-parity spike outcome
 * (see dashboard-modern/MEDICATION_PARITY_SPIKE.md):
 *   - If the FHIR-only split works, fetch MedicationRequest and filter
 *     in the adapter to the lists-row entries.
 *   - If the spike forces a fallback, the Standard REST endpoint
 *     /api/patient/:pid/medication is consulted (see AgDR-0085).
 *
 * Status filtering ("active" only) happens in the adapter.
 */
export async function getActiveMedications(
  _patientId: string,
): Promise<ReadonlyArray<MedicationDisplay>> {
  throw new Error('getActiveMedications(): not implemented — Workstream B')
}
