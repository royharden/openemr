import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { MedicationRequestSchema } from '@/fhir/schemas/medicationRequest'
import { adaptMedications } from '@/models/adapters/medications'
import type { MedicationDisplay } from '@/models/dashboard'

export async function getActiveMedications(patientId: string): Promise<ReadonlyArray<MedicationDisplay>> {
  const bundle = await fhirGet(
    `MedicationRequest?patient=${patientId}`,
    FhirBundleSchema,
  )
  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => MedicationRequestSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof MedicationRequestSchema>> => r.success)
    .map((r) => r.data)

  return adaptMedications(resources)
}
