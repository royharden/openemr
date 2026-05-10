import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream B fills in (per Phase 0 spike outcome). */
export function MedicationsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Medications</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading medications…" />
      </CardContent>
    </Card>
  )
}
