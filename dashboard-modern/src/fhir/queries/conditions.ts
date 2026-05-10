import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { ConditionSchema } from '@/fhir/schemas/condition'
import { adaptProblems } from '@/models/adapters/problems'
import type { ProblemDisplay } from '@/models/dashboard'

export async function getActiveProblems(patientId: string): Promise<ReadonlyArray<ProblemDisplay>> {
  const bundle = await fhirGet(
    `Condition?patient=${patientId}&category=problem-list-item`,
    FhirBundleSchema,
  )
  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => ConditionSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof ConditionSchema>> => r.success)
    .map((r) => r.data)

  return adaptProblems(resources)
}
