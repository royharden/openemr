/**
 * Typed FHIR request wrapper. Workstream A implements the body — W0 only
 * locks the function signatures so queries can compile.
 */
import type { z } from 'zod'

export type FhirGet = <T>(path: string, schema: z.ZodType<T>) => Promise<T>

/**
 * Returns the (cached) `fhirclient` Client instance. Implementation lands
 * in Workstream A — see master plan §7.
 */
export async function getClient(): Promise<unknown> {
  throw new Error('getClient(): not implemented — Workstream A')
}

/**
 * Issues a GET against the FHIR API via the SMART client and Zod-parses
 * the response. Implementation lands in Workstream A.
 */
export const fhirGet: FhirGet = async (_path, _schema) => {
  throw new Error('fhirGet(): not implemented — Workstream A')
}
