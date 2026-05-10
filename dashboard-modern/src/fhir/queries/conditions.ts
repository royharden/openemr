import type { ProblemDisplay } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Fetches Condition?patient={patientId}&category=problem-list-item.
 * `category` is a fundamental selector and OK to keep server-side.
 * `clinical-status` filtering happens in the adapter (NOT server-side).
 */
export async function getActiveProblems(_patientId: string): Promise<ReadonlyArray<ProblemDisplay>> {
  throw new Error('getActiveProblems(): not implemented — Workstream B')
}
