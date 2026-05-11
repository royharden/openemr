/**
 * URL helpers for local development.
 *
 * SMART authorization must use OpenEMR's real issuer URL. After OAuth returns
 * to the Vite dev server, browser-side FHIR reads can fail on CORS/TLS if they
 * call https://localhost:9300 directly. In dev, route those same-origin through
 * Vite's proxy while preserving the original OAuth issuer for authorization.
 */

const OPENEMR_BASE_URL = (import.meta.env.VITE_OPENEMR_BASE_URL as string | undefined) ?? ''

export function toDevProxyUrl(url: string): string {
  if (!import.meta.env.DEV || typeof window === 'undefined' || OPENEMR_BASE_URL === '') {
    return url
  }

  const base = OPENEMR_BASE_URL.replace(/\/$/, '')
  if (url !== base && !url.startsWith(`${base}/`)) {
    return url
  }

  return `${window.location.origin}${url.slice(base.length)}`
}
