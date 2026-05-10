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

const HumanNameSchema = z.object({
  use: z.string().optional(),
  text: z.string().optional(),
  family: z.string().optional(),
  given: z.array(z.string()).optional(),
  prefix: z.array(z.string()).optional(),
  suffix: z.array(z.string()).optional(),
})

export const PractitionerSchema = z
  .object({
    resourceType: z.literal('Practitioner'),
    id: z.string(),
    name: z.array(HumanNameSchema).optional(),
    qualification: z
      .array(
        z
          .object({
            code: CodeableConceptSchema.optional(),
          })
          .passthrough(),
      )
      .optional(),
  })
  .passthrough()

export type Practitioner = z.infer<typeof PractitionerSchema>

export function extractPractitionerName(p: Practitioner): string | null {
  const name = p.name?.[0]
  if (name == null) return null
  if (name.text != null) return name.text
  const given = name.given?.join(' ') ?? ''
  const family = name.family ?? ''
  const prefix = name.prefix?.join(' ') ?? ''
  const parts = [prefix, given, family].filter(Boolean)
  return parts.length > 0 ? parts.join(' ') : null
}
