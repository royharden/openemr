import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getActiveMedications } from '@/fhir/queries/medications'
import { getActivePrescriptions } from '@/fhir/queries/prescriptions'
import type { MedicationDisplay } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

function hasDrugConflict(med: MedicationDisplay, prescriptionDrugNames: ReadonlySet<string>): boolean {
  return prescriptionDrugNames.has(med.drug.toLowerCase())
}

function MedicationRow({
  med,
  conflict,
}: Readonly<{ med: MedicationDisplay; conflict: boolean }>) {
  return (
    <li className="flex flex-col gap-1 py-2 border-b border-neutral-100 last:border-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-sm">{med.drug}</span>
        <div className="flex gap-1 shrink-0">
          {conflict && (
            <Badge variant="warning" aria-label="Also appears in prescriptions">
              Duplicate Rx
            </Badge>
          )}
          <Badge variant="default" className="capitalize">
            {med.status}
          </Badge>
        </div>
      </div>
      <div className="flex gap-3 text-xs text-neutral-500 dark:text-neutral-400 flex-wrap">
        {med.dose != null && <span>Dose: {med.dose}</span>}
        {med.route != null && <span>Route: {med.route}</span>}
        {med.effectiveDate != null && <span>Since: {med.effectiveDate}</span>}
      </div>
    </li>
  )
}

export function MedicationsCard({ patientId }: Props) {
  const medsQuery = useQuery({
    queryKey: ['medications', patientId],
    queryFn: () => getActiveMedications(patientId),
    enabled: patientId !== '',
  })

  const rxQuery = useQuery({
    queryKey: ['prescriptions', patientId],
    queryFn: () => getActivePrescriptions(patientId),
    enabled: patientId !== '',
  })

  const prescriptionDrugNames: ReadonlySet<string> = new Set(
    (rxQuery.data ?? []).map((rx) => rx.drug.toLowerCase()),
  )

  const { data, isLoading, error } = medsQuery

  return (
    <Card>
      <CardHeader>
        <CardTitle>Medications</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading medications…" />}
        {error != null && (
          <ErrorState
            title="Failed to load medications"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.length === 0 && <EmptyState title="No active medications" />}
        {data != null && data.length > 0 && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800" aria-label="Active medications list">
            {data.map((med) => (
              <MedicationRow
                key={med.id}
                med={med}
                conflict={hasDrugConflict(med, prescriptionDrugNames)}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
