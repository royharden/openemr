import type { PatientHeaderData } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 * Reads /Patient/{patientId} and returns the view model.
 */
export async function getPatient(_patientId: string): Promise<PatientHeaderData> {
  throw new Error('getPatient(): not implemented — Workstream B')
}
