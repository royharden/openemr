import type { MedicationRequest } from '@/fhir/schemas/medicationRequest'
import type { MedicationDisplay, MedicationStatus } from '@/models/dashboard'

function resolveDrugName(resource: MedicationRequest): string {
  const med = resource.medicationCodeableConcept
  if (med != null) {
    return med.text ?? med.coding?.[0]?.display ?? med.coding?.[0]?.code ?? 'Unknown medication'
  }
  return resource.medicationReference?.display ?? 'Unknown medication'
}

function resolveDose(resource: MedicationRequest): string | null {
  const dosage = resource.dosageInstruction?.[0]
  if (dosage == null) return null
  if (dosage.text != null) return dosage.text
  const qty = dosage.doseAndRate?.[0]?.doseQuantity
  if (qty != null) {
    return `${qty.value ?? ''} ${qty.unit ?? ''}`.trim() || null
  }
  return null
}

function resolveRoute(resource: MedicationRequest): string | null {
  const dosage = resource.dosageInstruction?.[0]
  const route = dosage?.route
  if (route == null) return null
  return route.text ?? route.coding?.[0]?.display ?? null
}

function toMedStatus(status: string | undefined): MedicationStatus {
  const allowed = ['active', 'on-hold', 'cancelled', 'completed', 'entered-in-error', 'stopped', 'draft', 'unknown'] as const
  type S = typeof allowed[number]
  return allowed.includes(status as S) ? (status as S) : 'unknown'
}

export function adaptMedications(resources: ReadonlyArray<MedicationRequest>): ReadonlyArray<MedicationDisplay> {
  return resources
    .filter((r) => r.intent === 'plan' && r.status === 'active')
    .map((r) => ({
      id: r.id,
      drug: resolveDrugName(r),
      dose: resolveDose(r),
      route: resolveRoute(r),
      status: toMedStatus(r.status),
      effectiveDate: r.authoredOn ?? null,
      origin: 'list' as const,
    }))
}
