import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { ObservationSchema } from '@/fhir/schemas/observation'
import { adaptLabs } from '@/models/adapters/labs'
import type { LabResultDisplay } from '@/models/dashboard'

export async function getRecentLabResults(
  patientId: string,
  n: number = 10,
): Promise<ReadonlyArray<LabResultDisplay>> {
  const bundle = await fhirGet(
    `Observation?patient=${patientId}&category=laboratory&_count=${n}&_sort=-effectiveDateTime`,
    FhirBundleSchema,
  )

  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => ObservationSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof ObservationSchema>> => r.success)
    .map((r) => r.data)

  return adaptLabs(resources, n)
}
