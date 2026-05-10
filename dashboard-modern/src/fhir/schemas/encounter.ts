import { z } from 'zod'

// W0 stub — only used if the Lab Results section falls back to Encounter
// history per AgDR-0083.
export const EncounterSchema = z
  .object({
    resourceType: z.literal('Encounter'),
    id: z.string(),
  })
  .passthrough()

export type Encounter = z.infer<typeof EncounterSchema>
