import type { Patient } from '@/fhir/schemas/patient'
import type { PatientHeaderData, Sex } from '@/models/dashboard'

const NKDA_SNOMED = '716186003'

export { NKDA_SNOMED }

function computeAge(birthDate: string): number {
  const dob = new Date(birthDate)
  const today = new Date()
  let age = today.getFullYear() - dob.getFullYear()
  const m = today.getMonth() - dob.getMonth()
  if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) age--
  return age
}

function resolveMrn(resource: Patient): string {
  const identifiers = resource.identifier ?? []
  const mrn = identifiers.find(
    (id) =>
      id.system?.toLowerCase().includes('mrn') === true ||
      id.type?.coding?.some((c) => c.code === 'MR') === true,
  )
  return mrn?.value ?? identifiers[0]?.value ?? resource.id
}

function resolveFullName(resource: Patient): string {
  const names = resource.name ?? []
  const official = names.find((n) => n.use === 'official') ?? names[0]
  if (official == null) return 'Unknown Patient'
  if (official.text != null) return official.text
  const given = official.given?.join(' ') ?? ''
  const family = official.family ?? ''
  return `${given} ${family}`.trim() || 'Unknown Patient'
}

function resolveSex(gender: string | undefined): Sex {
  switch (gender) {
    case 'male':
      return 'male'
    case 'female':
      return 'female'
    case 'other':
      return 'other'
    default:
      return 'unknown'
  }
}

export function adaptPatientHeader(resource: Patient): PatientHeaderData {
  const dob = resource.birthDate ?? ''
  return {
    id: resource.id,
    fullName: resolveFullName(resource),
    dateOfBirth: dob,
    ageYears: dob !== '' ? computeAge(dob) : 0,
    sex: resolveSex(resource.gender),
    mrn: resolveMrn(resource),
    active: resource.active ?? true,
  }
}
