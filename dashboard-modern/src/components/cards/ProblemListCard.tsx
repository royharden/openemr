import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getActiveProblems } from '@/fhir/queries/conditions'
import type { ProblemDisplay } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

function formatDate(iso: string | null): string | null {
  if (iso == null) return null
  const [year, month, day] = iso.split('-')
  return `${month ?? '??'}/${day ?? '??'}/${year ?? '????'}`
}

function ProblemRow({ problem }: Readonly<{ problem: ProblemDisplay }>) {
  const codeLabel = problem.code != null ? `${problem.code}${problem.codeSystem != null ? ` (${problem.codeSystem.split('/').pop() ?? problem.codeSystem})` : ''}` : null

  return (
    <li className="flex flex-col gap-1 py-2 border-b border-neutral-100 last:border-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm">
          {codeLabel != null ? (
            <Tooltip content={<span className="font-mono">{codeLabel}</span>}>
              <span className="underline decoration-dotted cursor-help">{problem.display}</span>
            </Tooltip>
          ) : (
            problem.display
          )}
        </span>
        <Badge variant="default" className="shrink-0 capitalize">
          {problem.clinicalStatus}
        </Badge>
      </div>
      {problem.onset != null && (
        <p className="text-xs text-neutral-400">Onset: {formatDate(problem.onset)}</p>
      )}
    </li>
  )
}

export function ProblemListCard({ patientId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['problems', patientId],
    queryFn: () => getActiveProblems(patientId),
    enabled: patientId !== '',
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Problem List</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading problems…" />}
        {error != null && (
          <ErrorState
            title="Failed to load problem list"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.length === 0 && <EmptyState title="No active problems" />}
        {data != null && data.length > 0 && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800" aria-label="Active problems list">
            {data.map((problem) => (
              <ProblemRow key={problem.id} problem={problem} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
