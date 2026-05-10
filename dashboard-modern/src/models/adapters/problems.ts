import type { Condition } from '@/fhir/schemas/condition'
import type { ProblemDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Filters Conditions to clinicalStatus 'active' (CANONICAL — not server-
 * side). Resolves display via code.text → coding[0].display fallback.
 */
export function adaptProblems(
  _resources: ReadonlyArray<Condition>,
): ReadonlyArray<ProblemDisplay> {
  throw new Error('adaptProblems(): not implemented — Workstream B')
}
