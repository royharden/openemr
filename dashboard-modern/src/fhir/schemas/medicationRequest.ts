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

const DosageInstructionSchema = z
  .object({
    text: z.string().optional(),
    doseAndRate: z
      .array(
        z
          .object({
            doseQuantity: z
              .object({ value: z.number().optional(), unit: z.string().optional() })
              .passthrough()
              .optional(),
          })
          .passthrough(),
      )
      .optional(),
    route: CodeableConceptSchema.optional(),
  })
  .passthrough()

export const MedicationRequestSchema = z
  .object({
    resourceType: z.literal('MedicationRequest'),
    id: z.string(),
    status: z.string().optional(),
    intent: z.string().optional(),
    medicationCodeableConcept: CodeableConceptSchema.optional(),
    medicationReference: z
      .object({ reference: z.string().optional(), display: z.string().optional() })
      .passthrough()
      .optional(),
    authoredOn: z.string().optional(),
    dosageInstruction: z.array(DosageInstructionSchema).optional(),
    requester: z
      .object({
        reference: z.string().optional(),
        display: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough()

export type MedicationRequest = z.infer<typeof MedicationRequestSchema>
