import { z } from 'zod'

// W0 stub — Workstream C fills in.
export const CareTeamSchema = z
  .object({
    resourceType: z.literal('CareTeam'),
    id: z.string(),
  })
  .passthrough()

export type CareTeam = z.infer<typeof CareTeamSchema>
