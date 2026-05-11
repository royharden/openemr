import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'
import { ready } from '@/auth/smartClient'

/**
 * /index.html callback handler — completes the OAuth code exchange.
 *
 * fhirclient.ready() reads `code` and `state` from the URL, exchanges
 * the code for tokens, and stores the result in sessionStorage. On
 * success we navigate to /dashboard (replacing history so the back
 * button doesn't replay the callback).
 */
export function Callback() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [error, setError] = useState<Error | null>(null)
  const called = useRef(false)

  useEffect(() => {
    if (called.current) return
    called.current = true

    void (async () => {
      // Surface OAuth error params (e.g. access_denied from denied consent).
      const oauthError = searchParams.get('error')
      if (oauthError != null) {
        const desc = searchParams.get('error_description') ?? oauthError
        setError(new Error(`OAuth error: ${desc}`))
        return
      }

      try {
        await ready()
        const showSession = searchParams.get('showSession')
        const target = showSession != null ? `/dashboard?showSession=${showSession}` : '/dashboard'
        navigate(target, { replace: true })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('OAuth callback failed'))
      }
    })()
  }, [navigate, searchParams])

  if (error != null) return <ErrorState error={error} title="Could not complete sign-in" />
  return <LoadingSkeleton label="Completing sign-in…" />
}
