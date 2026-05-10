/**
 * Typed FHIR request wrapper (master plan §7, AgDR-0075).
 *
 * getClient() returns the cached fhirclient Client instance.
 * fhirGet<T>() issues a FHIR GET, Zod-parses the response, and returns
 * a typed value — the only way FHIR data enters the view-model layer.
 */

import type Client from 'fhirclient/lib/Client'
import { ready } from '@/auth/smartClient'
import { redact } from '@/auth/redact'
import { z } from 'zod'

export type FhirGet = <T>(path: string, schema: z.ZodType<T>) => Promise<T>

let cached: Client | null = null

export async function getClient(): Promise<Client> {
  if (cached !== null) return cached
  cached = await ready()
  return cached
}

/**
 * Issues a GET against the FHIR API via the SMART client and Zod-parses
 * the response. Throws if the parse fails.
 *
 * graph:false keeps fhirclient from auto-resolving references, which
 * would produce a deeply nested structure we don't expect in our schemas.
 */
export const fhirGet: FhirGet = async <T>(path: string, schema: z.ZodType<T>): Promise<T> => {
  const client = await getClient()

  let raw: unknown
  try {
    raw = await client.request(path, { graph: false })
  } catch (err) {
    console.error('[fhirGet] request failed', redact({ path, err }))
    throw err
  }

  const result = schema.safeParse(raw)
  if (!result.success) {
    console.error('[fhirGet] schema parse failed', redact({ path, issues: result.error.issues }))
    throw new Error(`FHIR parse error at ${path}: ${result.error.message}`)
  }

  return result.data
}
