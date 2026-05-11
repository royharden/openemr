import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DashboardGrid } from '@/components/DashboardGrid'
import { PatientHeader } from '@/components/PatientHeader'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'
import { getSession, EMPTY_SESSION, type Session } from '@/auth/session'
import { logout } from '@/auth/logout'
import { redact } from '@/auth/redact'

/**
 * Top-level dashboard layout.
 *
 * Reads the session from fhirclient state to get the patient context,
 * then renders PatientHeader + 6 clinical cards.
 *
 * When ?showSession=1 is present (grading/dev overlay), displays the
 * safe Session object { userId, patientContext, expiresAt } only.
 * No bearer token or PHI is shown.
 */
export function Dashboard() {
  const [searchParams] = useSearchParams()
  const showSession = searchParams.get('showSession') === '1'

  const [session, setSession] = useState<Session>(EMPTY_SESSION)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const s = await getSession()
        setSession(s)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Could not load session'))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl p-6">
        <LoadingSkeleton label="Loading dashboard…" />
      </main>
    )
  }

  if (error != null) {
    return (
      <main className="mx-auto max-w-7xl p-6">
        <ErrorState title="Session error — please sign in again" error={error} />
      </main>
    )
  }

  const patientId = session.patientContext ?? ''

  return (
    <main className="mx-auto max-w-7xl p-6 space-y-6" aria-busy={loading}>
      {showSession && (
        <div
          role="status"
          aria-label="Session info"
          className="rounded border border-amber-400 bg-amber-50 p-4 font-mono text-xs dark:bg-amber-950 dark:border-amber-700"
        >
          <pre>{JSON.stringify(redact(session), null, 2)}</pre>
        </div>
      )}

      <PatientHeader patientId={patientId} />
      <DashboardGrid patientId={patientId} />

      <div className="flex justify-end">
        <button
          type="button"
          className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
          onClick={() => { void logout() }}
        >
          Sign out
        </button>
      </div>
    </main>
  )
}
