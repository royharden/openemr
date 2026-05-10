import type { Patient } from '@/fhir/schemas/patient'
import type { PatientHeaderData } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Adapts a Zod-parsed FHIR Patient resource to the PatientHeaderData
 * view model. Computes age from birthDate. Resolves MRN from
 * identifier with system matching OpenEMR's MRN system.
 */
export function adaptPatientHeader(_resource: Patient): PatientHeaderData {
  throw new Error('adaptPatientHeader(): not implemented — Workstream B')
}
