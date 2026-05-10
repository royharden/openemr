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

const IdentifierSchema = z
  .object({
    system: z.string().optional(),
    value: z.string().optional(),
    type: CodeableConceptSchema.optional(),
  })
  .passthrough()

const HumanNameSchema = z
  .object({
    use: z.string().optional(),
    text: z.string().optional(),
    family: z.string().optional(),
    given: z.array(z.string()).optional(),
    prefix: z.array(z.string()).optional(),
  })
  .passthrough()

export const PatientSchema = z
  .object({
    resourceType: z.literal('Patient'),
    id: z.string(),
    active: z.boolean().optional(),
    name: z.array(HumanNameSchema).optional(),
    birthDate: z.string().optional(),
    gender: z.enum(['male', 'female', 'other', 'unknown']).optional(),
    identifier: z.array(IdentifierSchema).optional(),
  })
  .passthrough()

export type Patient = z.infer<typeof PatientSchema>
