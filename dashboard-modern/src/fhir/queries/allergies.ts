import type { AllergiesView } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Fetches AllergyIntolerance?patient={patientId}.
 *
 * MUST NOT add a server-side `clinical-status` filter — OpenEMR's FHIR
 * layer does not honor it. Status filtering happens in the adapter
 * (filterActiveAllergies / clinicalStatus.coding[*].code === 'active').
 *
 * NKDA detection: an explicit "no known allergies" record is preserved
 * in the AllergiesView via the `nkda` flag.
 */
export async function getActiveAllergies(_patientId: string): Promise<AllergiesView> {
  throw new Error('getActiveAllergies(): not implemented — Workstream B')
}
