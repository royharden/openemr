import { z } from 'zod'

// W0 stub — Workstream B fills in.
export const ConditionSchema = z
  .object({
    resourceType: z.literal('Condition'),
    id: z.string(),
  })
  .passthrough()

export type Condition = z.infer<typeof ConditionSchema>
