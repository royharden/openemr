import { Card, CardContent } from '@/components/ui/card'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'

/**
 * W0 stub — Workstream B implements the live header from PatientHeaderData.
 * The current shell renders a skeleton so the layout doesn't shift when
 * the real component lands.
 */
export function PatientHeader() {
  return (
    <Card>
      <CardContent className="p-6">
        <LoadingSkeleton rows={2} label="Loading patient header…" />
      </CardContent>
    </Card>
  )
}
