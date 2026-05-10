import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream B fills in. */
export function ProblemListCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Problem List</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading problems…" />
      </CardContent>
    </Card>
  )
}
