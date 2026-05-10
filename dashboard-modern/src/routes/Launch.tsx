import { useEffect, useState } from 'react'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'

/**
 * /launch route — entry point used by both EHR-launch and standalone-launch.
 * Calls FHIR.oauth2.authorize() with the configured SMART params; the
 * fhirclient library reads `iss` + `launch` from the URL automatically.
 *
 * W0 stub. Workstream A wires the real authorize() call.
 */
export function Launch() {
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const { authorize } = await import('@/auth/smartClient')
        await authorize()
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Launch failed'))
      }
    })()
  }, [])

  if (error) return <ErrorState error={error} title="Could not start SMART launch" />
  return <LoadingSkeleton label="Launching the patient dashboard…" />
}
