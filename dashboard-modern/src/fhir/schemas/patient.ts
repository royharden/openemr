import { z } from 'zod'

// W0 stub. Workstream B fleshes out the shape Maria G. actually returns.
// Keep `.passthrough()` so unknown FHIR fields don't fail Zod parse.
export const PatientSchema = z
  .object({
    resourceType: z.literal('Patient'),
    id: z.string(),
  })
  .passthrough()

export type Patient = z.infer<typeof PatientSchema>
