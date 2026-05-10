import { z } from 'zod'

/**
 * Generic FHIR Bundle skeleton. Workstreams B/C compose this with their
 * resource-specific schemas to validate search responses.
 */
export const FhirBundleEntrySchema = z
  .object({
    fullUrl: z.string().optional(),
    resource: z.unknown().optional(),
    search: z.object({ mode: z.string().optional() }).passthrough().optional(),
  })
  .passthrough()

export const FhirBundleSchema = z
  .object({
    resourceType: z.literal('Bundle'),
    type: z.string().optional(),
    total: z.number().optional(),
    entry: z.array(FhirBundleEntrySchema).optional(),
  })
  .passthrough()

export type FhirBundle = z.infer<typeof FhirBundleSchema>
