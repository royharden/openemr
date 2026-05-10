import { z } from 'zod'

// W0 stub — Workstream B fills in. Phase 0 spike outcome (see
// dashboard-modern/MEDICATION_PARITY_SPIKE.md) determines which fields
// are load-bearing for the lists-vs-prescriptions split.
export const MedicationRequestSchema = z
  .object({
    resourceType: z.literal('MedicationRequest'),
    id: z.string(),
  })
  .passthrough()

export type MedicationRequest = z.infer<typeof MedicationRequestSchema>
