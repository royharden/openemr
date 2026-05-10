import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'

/**
 * OAuth callback handler. fhirclient hands us a Client bound to the
 * launched patient context; we then route to /dashboard.
 *
 * W0 stub. Workstream A wires FHIR.oauth2.ready().
 */
export function Callback() {
  const navigate = useNavigate()
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const { ready } = await import('@/auth/smartClient')
        await ready()
        navigate('/dashboard', { replace: true })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('OAuth callback failed'))
      }
    })()
  }, [navigate])

  if (error) return <ErrorState error={error} title="Could not complete sign-in" />
  return <LoadingSkeleton label="Completing sign-in…" />
}
