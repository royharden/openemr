import type { PrescriptionDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream C implements the body.
 *
 * Fetches MedicationRequest?patient={patientId}.
 * Per Phase 0 spike, the adapter splits MedicationRequest into the
 * Prescriptions card vs the Medications card.
 *
 * Adapter resolves `requester.reference` → Practitioner.name via a
 * bounded follow-up read.
 */
export async function getActivePrescriptions(
  _patientId: string,
): Promise<ReadonlyArray<PrescriptionDisplay>> {
  throw new Error('getActivePrescriptions(): not implemented — Workstream C')
}
