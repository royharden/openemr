import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/** W0 stub — Workstream C fills in (or swaps to EncounterHistoryCard per AgDR-0083). */
export function LabResultsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Lab Results</CardTitle>
      </CardHeader>
      <CardContent>
        <LoadingSkeleton label="Loading lab results…" />
      </CardContent>
    </Card>
  )
}
