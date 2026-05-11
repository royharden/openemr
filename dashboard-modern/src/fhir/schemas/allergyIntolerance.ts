import { z } from 'zod'

const CodingSchema = z
  .object({
    system: z.string().optional(),
    code: z.string().optional(),
    display: z.string().optional(),
  })
  .passthrough()

const CodeableConceptSchema = z
  .object({
    coding: z.array(CodingSchema).optional(),
    text: z.string().optional(),
  })
  .passthrough()

const NarrativeSchema = z
  .object({
    status: z.string().optional(),
    div: z.string().optional(),
  })
  .passthrough()

const ReactionSchema = z
  .object({
    substance: CodeableConceptSchema.optional(),
    manifestation: z.array(CodeableConceptSchema).optional(),
    description: z.string().optional(),
    severity: z.string().optional(),
  })
  .passthrough()

export const AllergyIntoleranceSchema = z
  .object({
    resourceType: z.literal('AllergyIntolerance'),
    id: z.string(),
    clinicalStatus: CodeableConceptSchema.optional(),
    verificationStatus: CodeableConceptSchema.optional(),
    criticality: z.enum(['low', 'high', 'unable-to-assess']).optional(),
    text: NarrativeSchema.optional(),
    code: CodeableConceptSchema.optional(),
    recordedDate: z.string().optional(),
    reaction: z.array(ReactionSchema).optional(),
  })
  .passthrough()

export type AllergyIntolerance = z.infer<typeof AllergyIntoleranceSchema>
