import { fhirGet } from '@/fhir/client'
import { PatientSchema } from '@/fhir/schemas/patient'
import { adaptPatientHeader } from '@/models/adapters/patientHeader'
import type { PatientHeaderData } from '@/models/dashboard'

export async function getPatient(patientId: string): Promise<PatientHeaderData> {
  const resource = await fhirGet(`Patient/${patientId}`, PatientSchema)
  return adaptPatientHeader(resource)
}
