import { AllergiesCard } from '@/components/cards/AllergiesCard'
import { ProblemListCard } from '@/components/cards/ProblemListCard'
import { MedicationsCard } from '@/components/cards/MedicationsCard'
import { PrescriptionsCard } from '@/components/cards/PrescriptionsCard'
import { CareTeamCard } from '@/components/cards/CareTeamCard'
import { LabResultsCard } from '@/components/cards/LabResultsCard'

export function DashboardGrid() {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
      <AllergiesCard />
      <ProblemListCard />
      <MedicationsCard />
      <PrescriptionsCard />
      <CareTeamCard />
      <LabResultsCard />
    </div>
  )
}
