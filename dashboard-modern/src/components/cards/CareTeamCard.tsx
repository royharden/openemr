import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream C fills in. */
export function CareTeamCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Care Team</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading care team…" />
      </CardContent>
    </Card>
  )
}
