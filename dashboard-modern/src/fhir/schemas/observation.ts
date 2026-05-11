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

const QuantitySchema = z.object({
  value: z.number().optional(),
  unit: z.string().optional(),
  system: z.string().optional(),
  code: z.string().optional(),
})

const ReferenceRangeSchema = z
  .object({
    low: QuantitySchema.optional(),
    high: QuantitySchema.optional(),
    text: z.string().optional(),
  })
  .passthrough()

export const ObservationSchema = z
  .object({
    resourceType: z.literal('Observation'),
    id: z.string(),
    status: z
      .enum(['registered', 'preliminary', 'final', 'amended', 'corrected', 'cancelled', 'entered-in-error', 'unknown'])
      .optional(),
    category: z.array(CodeableConceptSchema).optional(),
    code: CodeableConceptSchema.optional(),
    effectiveDateTime: z.string().optional(),
    effectivePeriod: z
      .object({ start: z.string().optional(), end: z.string().optional() })
      .optional(),
    valueQuantity: QuantitySchema.optional(),
    valueString: z.string().optional(),
    valueCodeableConcept: CodeableConceptSchema.optional(),
    interpretation: z.array(CodeableConceptSchema).optional(),
    referenceRange: z.array(ReferenceRangeSchema).optional(),
    component: z
      .array(
        z
          .object({
            code: CodeableConceptSchema.optional(),
            valueQuantity: QuantitySchema.optional(),
            valueString: z.string().optional(),
          })
          .passthrough(),
      )
      .optional(),
  })
  .passthrough()

export type Observation = z.infer<typeof ObservationSchema>
