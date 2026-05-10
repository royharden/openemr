import type { AllergyIntolerance } from '@/fhir/schemas/allergyIntolerance'
import type { AllergiesView, AllergyDisplay, Criticality } from '@/models/dashboard'

const NKDA_SNOMED_CODE = '716186003'

function getClinicalStatusCode(resource: AllergyIntolerance): string {
  return resource.clinicalStatus?.coding?.find((c) => c.code != null)?.code ?? 'unknown'
}

function getVerificationStatusCode(resource: AllergyIntolerance): AllergyDisplay['verificationStatus'] {
  const code = resource.verificationStatus?.coding?.find((c) => c.code != null)?.code ?? 'unknown'
  const allowed = ['unconfirmed', 'presumed', 'confirmed', 'refuted', 'entered-in-error', 'unknown'] as const
  type V = typeof allowed[number]
  return allowed.includes(code as V) ? (code as V) : 'unknown'
}

function getCriticality(resource: AllergyIntolerance): Criticality {
  switch (resource.criticality) {
    case 'low':
      return 'low'
    case 'high':
      return 'high'
    case 'unable-to-assess':
      return 'unable-to-assess'
    default:
      return 'unknown'
  }
}

function getSubstance(resource: AllergyIntolerance): string {
  const code = resource.code
  if (code == null) return 'Unknown substance'
  return code.text ?? code.coding?.[0]?.display ?? code.coding?.[0]?.code ?? 'Unknown substance'
}

function getReactions(resource: AllergyIntolerance): ReadonlyArray<string> {
  return (
    resource.reaction?.flatMap((r) =>
      r.manifestation?.map((m) => m.text ?? m.coding?.[0]?.display ?? 'Unknown reaction') ?? [],
    ) ?? []
  )
}

function isNkda(resource: AllergyIntolerance): boolean {
  return resource.code?.coding?.some((c) => c.code === NKDA_SNOMED_CODE) === true
}

function toAllergyDisplay(resource: AllergyIntolerance): AllergyDisplay {
  const statusCode = getClinicalStatusCode(resource)
  const allowed = ['active', 'inactive', 'resolved', 'unknown'] as const
  type S = typeof allowed[number]
  const clinicalStatus: S = allowed.includes(statusCode as S) ? (statusCode as S) : 'unknown'

  return {
    id: resource.id,
    substance: getSubstance(resource),
    clinicalStatus,
    verificationStatus: getVerificationStatusCode(resource),
    criticality: getCriticality(resource),
    reactions: getReactions(resource),
    recordedDate: resource.recordedDate ?? null,
  }
}

export function adaptAllergies(resources: ReadonlyArray<AllergyIntolerance>): AllergiesView {
  if (resources.length === 1 && isNkda(resources[0]!)) {
    return { nkda: true, items: [] }
  }

  const active = resources.filter((r) => getClinicalStatusCode(r) === 'active')

  return {
    nkda: false,
    items: active.map(toAllergyDisplay),
  }
}
