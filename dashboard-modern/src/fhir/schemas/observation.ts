import { z } from 'zod'

// W0 stub — Workstream C fills in.
export const ObservationSchema = z
  .object({
    resourceType: z.literal('Observation'),
    id: z.string(),
  })
  .passthrough()

export type Observation = z.infer<typeof ObservationSchema>
