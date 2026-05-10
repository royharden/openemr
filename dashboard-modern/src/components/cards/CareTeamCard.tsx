import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { EmptyState } from '@/components/states/EmptyState'
import { ErrorState } from '@/components/states/ErrorState'
import { getActiveCareTeam } from '@/fhir/queries/careTeam'
import type { CareTeamDisplay, CareTeamMember } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

function MemberRow({ member }: Readonly<{ member: CareTeamMember }>) {
  return (
    <li className="flex items-center gap-2 py-1.5 text-sm">
      <span className="font-medium">{member.name ?? 'Unknown provider'}</span>
      {member.role != null && (
        <Badge variant="outline" className="text-xs">
          {member.role}
        </Badge>
      )}
    </li>
  )
}

function CareTeamSection({ team }: Readonly<{ team: CareTeamDisplay }>) {
  return (
    <div className="mb-4 last:mb-0">
      {team.name != null && (
        <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wide mb-1 dark:text-neutral-400">
          {team.name}
        </p>
      )}
      {team.members.length === 0 ? (
        <p className="text-xs text-neutral-400 italic">No members listed</p>
      ) : (
        <ul aria-label={`Members of ${team.name ?? 'care team'}`}>
          {team.members.map((m) => (
            <MemberRow key={m.id} member={m} />
          ))}
        </ul>
      )}
    </div>
  )
}

export function CareTeamCard({ patientId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['careTeam', patientId],
    queryFn: () => getActiveCareTeam(patientId),
    enabled: patientId !== '',
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Care Team</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingSkeleton label="Loading care team…" />}
        {error != null && (
          <ErrorState
            title="Failed to load care team"
            error={error instanceof Error ? error : new Error(String(error))}
          />
        )}
        {data != null && data.length === 0 && (
          <EmptyState title="No active care teams on record" />
        )}
        {data != null && data.length > 0 && (
          <div aria-label="Active care teams">
            {data.map((team) => (
              <CareTeamSection key={team.id} team={team} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
