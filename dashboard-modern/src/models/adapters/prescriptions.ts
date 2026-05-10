import type { MedicationRequest } from '@/fhir/schemas/medicationRequest'
import type { MedicationStatus, PrescriptionDisplay } from '@/models/dashboard'

function resolveDrugName(resource: MedicationRequest): string {
  const med = resource.medicationCodeableConcept
  if (med != null) {
    return med.text ?? med.coding?.[0]?.display ?? med.coding?.[0]?.code ?? 'Unknown medication'
  }
  return resource.medicationReference?.display ?? 'Unknown medication'
}

function resolveSig(resource: MedicationRequest): string | null {
  const dosage = resource.dosageInstruction?.[0]
  if (dosage == null) return null
  if (dosage.text != null) return dosage.text
  const qty = dosage.doseAndRate?.[0]?.doseQuantity
  if (qty != null) {
    return `${qty.value ?? ''} ${qty.unit ?? ''}`.trim() || null
  }
  return null
}

function toMedStatus(status: string | undefined): MedicationStatus {
  const allowed = [
    'active',
    'on-hold',
    'cancelled',
    'completed',
    'entered-in-error',
    'stopped',
    'draft',
    'unknown',
  ] as const
  type S = (typeof allowed)[number]
  return allowed.includes(status as S) ? (status as S) : 'unknown'
}

export function adaptPrescriptions(
  resources: ReadonlyArray<MedicationRequest>,
  practitionerNamesById: ReadonlyMap<string, string>,
): ReadonlyArray<PrescriptionDisplay> {
  return resources
    .filter((r) => r.intent === 'order' && r.status === 'active')
    .map((r) => {
      const requesterRef = r.requester?.reference ?? null
      let prescriberName: string | null = r.requester?.display ?? null

      if (requesterRef != null) {
        const practId = requesterRef.startsWith('Practitioner/')
          ? requesterRef.slice('Practitioner/'.length)
          : requesterRef
        const resolved = practitionerNamesById.get(practId)
        if (resolved != null) prescriberName = resolved
      }

      return {
        id: r.id,
        drug: resolveDrugName(r),
        sig: resolveSig(r),
        status: toMedStatus(r.status),
        authoredOn: r.authoredOn ?? null,
        prescriberName,
      }
    })
}
