import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream C fills in. */
export function PrescriptionsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prescriptions</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading prescriptions…" />
      </CardContent>
    </Card>
  )
}
