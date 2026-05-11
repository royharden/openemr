import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { MedicationRequestSchema } from '@/fhir/schemas/medicationRequest'
import { PractitionerSchema, extractPractitionerName } from '@/fhir/schemas/practitioner'
import { adaptPrescriptions } from '@/models/adapters/prescriptions'
import type { PrescriptionDisplay } from '@/models/dashboard'

async function resolvePractitioner(
  practitionerId: string,
): Promise<[string, string] | null> {
  try {
    const pract = await fhirGet(`Practitioner/${practitionerId}`, PractitionerSchema)
    const name = extractPractitionerName(pract)
    return name != null ? [practitionerId, name] : null
  } catch {
    return null
  }
}

export async function getActivePrescriptions(
  patientId: string,
): Promise<ReadonlyArray<PrescriptionDisplay>> {
  const bundle = await fhirGet(
    `MedicationRequest?patient=${patientId}`,
    FhirBundleSchema,
  )

  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => MedicationRequestSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof MedicationRequestSchema>> => r.success)
    .map((r) => r.data)
    .filter((r) => r.intent === 'order' && r.status === 'active')

  const practitionerIds = [
    ...new Set(
      resources
        .map((r) => {
          const ref = r.requester?.reference
          if (ref == null) return null
          return ref.startsWith('Practitioner/')
            ? ref.slice('Practitioner/'.length)
            : ref
        })
        .filter((id): id is string => id != null),
    ),
  ]

  const PARALLELISM_CAP = 3
  const nameEntries: Array<[string, string]> = []
  for (let i = 0; i < practitionerIds.length; i += PARALLELISM_CAP) {
    const batch = practitionerIds.slice(i, i + PARALLELISM_CAP)
    const results = await Promise.all(batch.map(resolvePractitioner))
    for (const r of results) {
      if (r != null) nameEntries.push(r)
    }
  }

  const practitionerNamesById = new Map(nameEntries)
  return adaptPrescriptions(resources, practitionerNamesById)
}
