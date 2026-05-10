import { z } from 'zod'

const CodingSchema = z.object({
  system: z.string().optional(),
  code: z.string().optional(),
  display: z.string().optional(),
})

const CodeableConceptSchema = z.object({
  coding: z.array(CodingSchema).optional(),
  text: z.string().optional(),
})

const ReferenceSchema = z.object({
  reference: z.string().optional(),
  display: z.string().optional(),
})

const ParticipantSchema = z
  .object({
    role: z.array(CodeableConceptSchema).optional(),
    member: ReferenceSchema.optional(),
  })
  .passthrough()

export const CareTeamSchema = z
  .object({
    resourceType: z.literal('CareTeam'),
    id: z.string(),
    status: z
      .enum(['proposed', 'active', 'suspended', 'inactive', 'entered-in-error'])
      .optional(),
    name: z.string().optional(),
    participant: z.array(ParticipantSchema).optional(),
  })
  .passthrough()

export type CareTeam = z.infer<typeof CareTeamSchema>
