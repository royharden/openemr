import { useEffect, useRef, useState } from 'react'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'
import { authorize } from '@/auth/smartClient'

/**
 * /launch route — entry point for both EHR-launch and standalone-launch.
 *
 * fhirclient reads `iss` and `launch` from the URL query string automatically:
 * - EHR-launch:        /launch.html?iss=...&launch=...   (OpenEMR injects both)
 * - Standalone-launch: /launch.html?iss=...              (user navigates directly)
 *
 * authorize() redirects the browser to OpenEMR's /oauth2/default/authorize,
 * so nothing after it runs — React renders the loading skeleton briefly.
 */
export function Launch() {
  const [error, setError] = useState<Error | null>(null)
  const called = useRef(false)

  useEffect(() => {
    // Guard against React StrictMode double-invocation.
    if (called.current) return
    called.current = true

    void (async () => {
      try {
        await authorize()
        // authorize() redirects; we only reach here in mocked tests.
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Launch failed'))
      }
    })()
  }, [])

  if (error != null) return <ErrorState error={error} title="Could not start SMART launch" />
  return <LoadingSkeleton label="Launching the patient dashboard…" />
}
