import { useQuery } from '@tanstack/react-query'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'
import { getPatient } from '@/fhir/queries/patient'
import type { PatientHeaderData } from '@/models/dashboard'

type Props = Readonly<{ patientId: string }>

function formatDob(iso: string): string {
  if (!iso) return 'Unknown'
  const [year, month, day] = iso.split('-')
  return `${month ?? '??'}/${day ?? '??'}/${year ?? '????'}`
}

function PatientHeaderContent({ data }: Readonly<{ data: PatientHeaderData }>) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{data.fullName}</h1>
        <div className="flex flex-wrap gap-3 mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          <span>DOB: {formatDob(data.dateOfBirth)}</span>
          <span aria-hidden>·</span>
          <span>Age: {data.ageYears} yrs</span>
          <span aria-hidden>·</span>
          <span className="capitalize">{data.sex}</span>
          <span aria-hidden>·</span>
          <span>MRN: {data.mrn}</span>
        </div>
      </div>
      <div>
        {data.active ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="warning">Inactive</Badge>
        )}
      </div>
    </div>
  )
}

export function PatientHeader({ patientId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['patient', patientId],
    queryFn: () => getPatient(patientId),
    enabled: patientId !== '',
  })

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <LoadingSkeleton rows={2} label="Loading patient header…" />
        </CardContent>
      </Card>
    )
  }

  if (error != null) {
    return (
      <Card>
        <CardContent className="p-6">
          <ErrorState title="Failed to load patient" error={error instanceof Error ? error : new Error(String(error))} />
        </CardContent>
      </Card>
    )
  }

  if (data == null) {
    return (
      <Card>
        <CardContent className="p-6">
          <LoadingSkeleton rows={2} label="Loading patient header…" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="p-6">
        <PatientHeaderContent data={data} />
      </CardContent>
    </Card>
  )
}
