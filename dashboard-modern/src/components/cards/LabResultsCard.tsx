import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getRecentLabResults } from '@/fhir/queries/observations'
import type { LabInterpretation, LabResultDisplay } from '@/models/dashboard'

type Props = Readonly<{ patientId: string; limit?: number }>

type BadgeVariant = 'danger' | 'warning' | 'success' | 'default'

const INTERP_VARIANT: Record<LabInterpretation, BadgeVariant> = {
  'critical-high': 'danger',
  'critical-low': 'danger',
  high: 'warning',
  low: 'warning',
  abnormal: 'warning',
  normal: 'success',
  unknown: 'default',
}

const INTERP_LABEL: Record<LabInterpretation, string> = {
  'critical-high': 'HH',
  'critical-low': 'LL',
  high: 'H',
  low: 'L',
  abnormal: 'A',
  normal: 'N',
  unknown: '?',
}

function LabRow({ lab }: Readonly<{ lab: LabResultDisplay }>) {
  const showBadge = lab.interpretation !== 'normal' && lab.interpretation !== 'unknown'
  const variant = INTERP_VARIANT[lab.interpretation]
  const label = INTERP_LABEL[lab.interpretation]

  return (
    <li className="flex flex-col gap-1 py-2 border-b border-neutral-100 last:border-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm">{lab.display}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          {lab.value != null && (
            <span className="text-sm font-mono">{lab.value}</span>
          )}
          {showBadge && (
            <Badge variant={variant} aria-label={`Interpretation: ${lab.interpretation}`}>
              {label}
            </Badge>
          )}
        </div>
      </div>
      <div className="flex gap-4 text-xs text-neutral-400">
        {lab.referenceRange != null && (
          <span>Range: {lab.referenceRange}</span>
        )}
        {lab.effectiveDateTime != null && (
          <span>{lab.effectiveDateTime.slice(0, 10)}</span>
        )}
      </div>
    </li>
  )
}

export function LabResultsCard({ patientId, limit = 10 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['labResults', patientId, limit],
    queryFn: () => getRecentLabResults(patientId, limit),
    enabled: patientId !== '',
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Lab Results</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading lab results…" />}
        {error != null && (
          <ErrorState
            title="Failed to load lab results"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.length === 0 && (
          <EmptyState title="No recent lab results" />
        )}
        {data != null && data.length > 0 && (
          <ul
            className="divide-y divide-neutral-100 dark:divide-neutral-800"
            aria-label="Recent lab results list"
          >
            {data.map((lab) => (
              <LabRow key={lab.id} lab={lab} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
