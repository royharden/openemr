import { z } from 'zod'

// W0 stub — Workstream C fills in (per-participant follow-up reads
// resolve names from this resource).
export const PractitionerSchema = z
  .object({
    resourceType: z.literal('Practitioner'),
    id: z.string(),
  })
  .passthrough()

export type Practitioner = z.infer<typeof PractitionerSchema>
