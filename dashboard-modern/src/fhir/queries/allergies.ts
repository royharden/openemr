import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { AllergyIntoleranceSchema } from '@/fhir/schemas/allergyIntolerance'
import { adaptAllergies } from '@/models/adapters/allergies'
import type { AllergiesView } from '@/models/dashboard'

export async function getActiveAllergies(patientId: string): Promise<AllergiesView> {
  const bundle = await fhirGet(
    `AllergyIntolerance?patient=${patientId}`,
    FhirBundleSchema,
  )
  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => AllergyIntoleranceSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof AllergyIntoleranceSchema>> => r.success)
    .map((r) => r.data)

  return adaptAllergies(resources)
}
