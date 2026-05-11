import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getActivePrescriptions } from '@/fhir/queries/prescriptions'
import type { PrescriptionDisplay } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

function PrescriptionRow({ rx }: Readonly<{ rx: PrescriptionDisplay }>) {
  return (
    <li className="flex flex-col gap-1 py-2 border-b border-neutral-100 last:border-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm">{rx.drug}</span>
        <Badge variant={rx.status === 'active' ? 'success' : 'default'}>{rx.status}</Badge>
      </div>
      {rx.sig != null && (
        <p className="text-xs text-neutral-600 dark:text-neutral-300">{rx.sig}</p>
      )}
      <div className="flex gap-4 text-xs text-neutral-400">
        {rx.authoredOn != null && <span>Prescribed: {rx.authoredOn}</span>}
        {rx.prescriberName != null && <span>By: {rx.prescriberName}</span>}
      </div>
    </li>
  )
}

export function PrescriptionsCard({ patientId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['prescriptions', patientId],
    queryFn: () => getActivePrescriptions(patientId),
    enabled: patientId !== '',
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prescriptions</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading prescriptions…" />}
        {error != null && (
          <ErrorState
            title="Failed to load prescriptions"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.length === 0 && (
          <EmptyState title="No active prescriptions" />
        )}
        {data != null && data.length > 0 && (
          <ul
            className="divide-y divide-neutral-100 dark:divide-neutral-800"
            aria-label="Active prescriptions list"
          >
            {data.map((rx) => (
              <PrescriptionRow key={rx.id} rx={rx} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
