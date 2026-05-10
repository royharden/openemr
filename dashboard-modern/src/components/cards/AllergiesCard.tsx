import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream B fills in. */
export function AllergiesCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Allergies</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading allergies…" />
      </CardContent>
    </Card>
  )
}
