/**
 * Redaction utility for any object before it crosses a logging boundary.
 *
 * Workstream A finalizes the rules. The W0 stub already redacts the
 * obvious bearer-token keys so the placeholder is never accidentally
 * logged with a real token attached.
 */

const TOKEN_KEYS = new Set([
  'access_token',
  'accessToken',
  'refresh_token',
  'refreshToken',
  'id_token',
  'idToken',
  'authorization',
  'Authorization',
])

const PHI_KEYS = new Set([
  'name',
  'birthDate',
  'dateOfBirth',
  'mrn',
  'ssn',
  'address',
  'telecom',
])

export function redact<T>(input: T): T {
  if (input == null || typeof input !== 'object') return input
  if (Array.isArray(input)) {
    return input.map(redact) as unknown as T
  }
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
    if (TOKEN_KEYS.has(key)) {
      out[key] = '[REDACTED_TOKEN]'
    } else if (PHI_KEYS.has(key)) {
      out[key] = '[REDACTED_PHI]'
    } else {
      out[key] = redact(value)
    }
  }
  return out as T
}
