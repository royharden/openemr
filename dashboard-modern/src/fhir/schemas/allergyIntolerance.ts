import { z } from 'zod'

// W0 stub — Workstream B fills in.
export const AllergyIntoleranceSchema = z
  .object({
    resourceType: z.literal('AllergyIntolerance'),
    id: z.string(),
  })
  .passthrough()

export type AllergyIntolerance = z.infer<typeof AllergyIntoleranceSchema>
