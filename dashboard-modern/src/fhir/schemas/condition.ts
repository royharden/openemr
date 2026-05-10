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

export const ConditionSchema = z
  .object({
    resourceType: z.literal('Condition'),
    id: z.string(),
    clinicalStatus: CodeableConceptSchema.optional(),
    verificationStatus: CodeableConceptSchema.optional(),
    category: z.array(CodeableConceptSchema).optional(),
    code: CodeableConceptSchema.optional(),
    onsetDateTime: z.string().optional(),
    recordedDate: z.string().optional(),
  })
  .passthrough()

export type Condition = z.infer<typeof ConditionSchema>
