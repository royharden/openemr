import { AllergiesCard } from '@/components/cards/AllergiesCard'
import { ProblemListCard } from '@/components/cards/ProblemListCard'
import { MedicationsCard } from '@/components/cards/MedicationsCard'
import { PrescriptionsCard } from '@/components/cards/PrescriptionsCard'
import { CareTeamCard } from '@/components/cards/CareTeamCard'
import { LabResultsCard } from '@/components/cards/LabResultsCard'

type Props = Readonly<{ patientId: string }>

export function DashboardGrid({ patientId }: Props) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
      <AllergiesCard patientId={patientId} />
      <ProblemListCard patientId={patientId} />
      <MedicationsCard patientId={patientId} />
      <PrescriptionsCard patientId={patientId} />
      <CareTeamCard patientId={patientId} />
      <LabResultsCard patientId={patientId} />
    </div>
  )
}
