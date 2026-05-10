import type { Condition } from '@/fhir/schemas/condition'
import type { ProblemDisplay } from '@/models/dashboard'

function getClinicalStatusCode(resource: Condition): string {
  return resource.clinicalStatus?.coding?.find((c) => c.code != null)?.code ?? 'unknown'
}

function resolveDisplay(resource: Condition): string {
  const code = resource.code
  if (code == null) return 'Unknown problem'
  return code.text ?? code.coding?.[0]?.display ?? code.coding?.[0]?.code ?? 'Unknown problem'
}

function resolveCode(resource: Condition): string | null {
  return resource.code?.coding?.[0]?.code ?? null
}

function resolveCodeSystem(resource: Condition): string | null {
  return resource.code?.coding?.[0]?.system ?? null
}

function toClinicalStatus(code: string): ProblemDisplay['clinicalStatus'] {
  const allowed = ['active', 'recurrence', 'relapse', 'inactive', 'remission', 'resolved', 'unknown'] as const
  type S = typeof allowed[number]
  return allowed.includes(code as S) ? (code as S) : 'unknown'
}

export function adaptProblems(resources: ReadonlyArray<Condition>): ReadonlyArray<ProblemDisplay> {
  return resources
    .filter((r) => getClinicalStatusCode(r) === 'active')
    .map((r) => ({
      id: r.id,
      display: resolveDisplay(r),
      code: resolveCode(r),
      codeSystem: resolveCodeSystem(r),
      clinicalStatus: toClinicalStatus(getClinicalStatusCode(r)),
      onset: r.onsetDateTime ?? null,
      recordedDate: r.recordedDate ?? null,
    }))
}
