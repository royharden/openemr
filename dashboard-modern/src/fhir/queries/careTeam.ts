import { z } from 'zod'
import { fhirGet } from '@/fhir/client'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'
import { CareTeamSchema } from '@/fhir/schemas/careTeam'
import { PractitionerSchema, extractPractitionerName } from '@/fhir/schemas/practitioner'
import { adaptCareTeam } from '@/models/adapters/careTeam'
import type { CareTeamDisplay } from '@/models/dashboard'

const PARALLELISM_CAP = 3

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

export async function getActiveCareTeam(
  patientId: string,
): Promise<ReadonlyArray<CareTeamDisplay>> {
  const bundle = await fhirGet(
    `CareTeam?patient=${patientId}`,
    FhirBundleSchema,
  )

  const resources = (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => CareTeamSchema.safeParse(raw))
    .filter((r): r is z.SafeParseSuccess<z.infer<typeof CareTeamSchema>> => r.success)
    .map((r) => r.data)

  const activeResources = resources.filter((r) => r.status === 'active')

  const practitionerIds = [
    ...new Set(
      activeResources.flatMap((r) =>
        (r.participant ?? [])
          .map((p) => {
            const ref = p.member?.reference
            if (ref == null) return null
            return ref.startsWith('Practitioner/')
              ? ref.slice('Practitioner/'.length)
              : ref
          })
          .filter((id): id is string => id != null),
      ),
    ),
  ]

  const nameEntries: Array<[string, string]> = []
  for (let i = 0; i < practitionerIds.length; i += PARALLELISM_CAP) {
    const batch = practitionerIds.slice(i, i + PARALLELISM_CAP)
    const results = await Promise.all(batch.map(resolvePractitioner))
    for (const r of results) {
      if (r != null) nameEntries.push(r)
    }
  }

  const practitionerNamesById = new Map(nameEntries)
  return adaptCareTeam(resources, practitionerNamesById)
}
