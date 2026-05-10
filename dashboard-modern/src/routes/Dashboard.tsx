import { DashboardGrid } from '@/components/DashboardGrid'
import { PatientHeader } from '@/components/PatientHeader'

/**
 * Top-level dashboard layout. The header + 6 cards.
 *
 * W0 renders skeletons. Workstreams B and C populate the cards via the
 * locked-signature query functions.
 */
export function Dashboard() {
  return (
    <main className="mx-auto max-w-7xl p-6 space-y-6">
      <PatientHeader />
      <DashboardGrid />
    </main>
  )
}
