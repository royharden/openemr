import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getActiveAllergies } from '@/fhir/queries/allergies'
import type { AllergyDisplay } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

const CRITICALITY_VARIANT: Record<string, 'danger' | 'warning' | 'default'> = {
  high: 'danger',
  low: 'warning',
  'unable-to-assess': 'default',
  unknown: 'default',
}

function AllergyRow({ allergy }: Readonly<{ allergy: AllergyDisplay }>) {
  const critVariant = CRITICALITY_VARIANT[allergy.criticality] ?? 'default'
  return (
    <li className="flex flex-col gap-1 py-2 border-b border-neutral-100 last:border-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm">{allergy.substance}</span>
        <Badge variant={critVariant} className="shrink-0">
          {allergy.criticality}
        </Badge>
      </div>
      {allergy.reactions.length > 0 && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Reactions: {allergy.reactions.join(', ')}
        </p>
      )}
      {allergy.recordedDate != null && (
        <p className="text-xs text-neutral-400">Recorded: {allergy.recordedDate}</p>
      )}
    </li>
  )
}

export function AllergiesCard({ patientId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['allergies', patientId],
    queryFn: () => getActiveAllergies(patientId),
    enabled: patientId !== '',
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Allergies</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading allergies…" />}
        {error != null && (
          <ErrorState
            title="Failed to load allergies"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.nkda && (
          <Badge variant="success" aria-label="No Known Drug Allergies">
            NKDA — No Known Drug Allergies
          </Badge>
        )}
        {data != null && !data.nkda && data.items.length === 0 && (
          <EmptyState title="No active allergies" />
        )}
        {data != null && !data.nkda && data.items.length > 0 && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800" aria-label="Active allergies list">
            {data.items.map((allergy) => (
              <AllergyRow key={allergy.id} allergy={allergy} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
