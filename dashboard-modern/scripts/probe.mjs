#!/usr/bin/env node
/**
 * W0 live-probe driver.
 *
 * Drives the SMART-on-FHIR auth_code + PKCE flow against the local OpenEMR
 * Docker stack using Playwright to navigate the OAuth login screen, then
 * captures the access_token and runs the three Phase 0 / W0 probes:
 *
 *   1. Phase 0 medication-parity:
 *        GET /apis/default/fhir/MedicationRequest?patient=<uuid>
 *      → inspect entries; verify the `intent` field discriminates
 *        prescriptions (`order`) from lists-row meds (`plan`).
 *
 *   2. CareTeam `_include`:
 *        GET /apis/default/fhir/CareTeam?patient=<uuid>
 *        GET /apis/default/fhir/CareTeam?patient=<uuid>&_include=CareTeam:participant
 *      → diff the bundle; does the `_include` request actually pull in
 *        Practitioner resources?
 *
 *   3. Server-side status filter:
 *        GET /apis/default/fhir/AllergyIntolerance?patient=<uuid>
 *        GET /apis/default/fhir/AllergyIntolerance?patient=<uuid>&clinical-status=active
 *      → diff the bundle; is the server-side status filter honored?
 *
 * Outputs a markdown summary at agentdocs/probe-results/probe.json.
 *
 * USAGE:
 *   node scripts/probe.mjs
 *
 * Reads VITE_* env from .env.local. Disables TLS verification (self-signed cert).
 */

import { chromium } from 'playwright'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { createHash, randomBytes } from 'node:crypto'

const __dirname = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(__dirname, '..')

// ── env loader ───────────────────────────────────────────────────────────────
function loadEnv(file) {
  const text = readFileSync(resolve(projectRoot, file), 'utf8')
  const out = {}
  for (const line of text.split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)$/.exec(line)
    if (m) out[m[1]] = m[2].replace(/^"|"$/g, '')
  }
  return out
}
const env = loadEnv('.env.local')

const OPENEMR_BASE = env.VITE_OPENEMR_BASE_URL || 'https://localhost:9300'
const FHIR_BASE = env.VITE_OPENEMR_FHIR_BASE_URL || `${OPENEMR_BASE}/apis/default/fhir`
const CLIENT_ID = env.VITE_SMART_CLIENT_ID
// For probing, prepend `launch/patient` so OpenEMR shows the patient picker
// (we have no real EHR launch context here).
const SCOPES = `launch/patient ${env.VITE_DEFAULT_SCOPES}`.trim()
const REDIRECT_URI = 'http://localhost:5173/index.html'
const ADMIN_USER = process.env.OPENEMR_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.OPENEMR_ADMIN_PASS || 'pass'

if (!CLIENT_ID) {
  console.error('VITE_SMART_CLIENT_ID missing from .env.local')
  process.exit(1)
}

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0' // self-signed cert

// ── PKCE ─────────────────────────────────────────────────────────────────────
function base64UrlEncode(buf) {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
const codeVerifier = base64UrlEncode(randomBytes(32))
const codeChallenge = base64UrlEncode(createHash('sha256').update(codeVerifier).digest())
const state = base64UrlEncode(randomBytes(16))

const authorizeUrl = new URL(`${OPENEMR_BASE}/oauth2/default/authorize`)
authorizeUrl.searchParams.set('response_type', 'code')
authorizeUrl.searchParams.set('client_id', CLIENT_ID)
authorizeUrl.searchParams.set('redirect_uri', REDIRECT_URI)
authorizeUrl.searchParams.set('scope', SCOPES)
authorizeUrl.searchParams.set('state', state)
authorizeUrl.searchParams.set('code_challenge', codeChallenge)
authorizeUrl.searchParams.set('code_challenge_method', 'S256')
authorizeUrl.searchParams.set('aud', FHIR_BASE)

console.log('[probe] starting headless OAuth dance via Playwright')
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ ignoreHTTPSErrors: true })
const page = await context.newPage()

let authCode = null
let pageError = null

// Catch the redirect to localhost:5173/index.html — never actually fetched
// because nothing's listening there during the probe.
page.on('framenavigated', (frame) => {
  const url = frame.url()
  if (url.startsWith(REDIRECT_URI)) {
    const u = new URL(url)
    authCode = u.searchParams.get('code')
  }
})
page.on('request', (req) => {
  const url = req.url()
  // Trace all top-level navigations.
  if (req.isNavigationRequest()) {
    console.log(`[trace] ${req.method()} ${url}`)
  }
  if (url.startsWith(REDIRECT_URI)) {
    const u = new URL(url)
    const c = u.searchParams.get('code')
    if (c) authCode = c
  }
})
page.on('response', (resp) => {
  const status = resp.status()
  const url = resp.url()
  if (status >= 300 && status < 400) {
    const loc = resp.headers()['location']
    console.log(`[trace] ${status} from ${url} -> ${loc ?? '(no location)'}`)
  }
})
await context.route('http://localhost:5173/**', async (route) => {
  const u = new URL(route.request().url())
  const c = u.searchParams.get('code')
  if (c) authCode = c
  await route.fulfill({ status: 200, body: '<!doctype html><meta charset="utf-8"><title>probe ok</title>' })
})

async function dumpPage(label) {
  const url = page.url()
  const title = await page.title().catch(() => '<no title>')
  const html = await page.content().catch(() => '<no content>')
  const snippet = html.replace(/\s+/g, ' ').slice(0, 800)
  console.log(`[probe:${label}] url=${url}`)
  console.log(`[probe:${label}] title=${title}`)
  console.log(`[probe:${label}] html-snippet=${snippet}`)
}

try {
  await page.goto(authorizeUrl.toString(), { waitUntil: 'domcontentloaded' })
  await dumpPage('after-authorize')

  // OpenEMR login screen — admin / pass.
  const userField = page.locator('input[name="username"], input[name="authUser"], input#authUser').first()
  const passField = page.locator('input[name="password"], input[name="clearPass"], input#clearPass').first()
  if (await userField.count()) {
    await userField.fill(ADMIN_USER)
    await passField.fill(ADMIN_PASS)
    const submit = page.locator('button[type="submit"], input[type="submit"]').first()
    await Promise.all([
      page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {}),
      submit.click({ force: true }).catch(() => {}),
    ])
    await dumpPage('after-login-submit')
  } else {
    console.log('[probe] no login form detected at /authorize landing — already authed?')
  }

  // Authorize / consent screen — accept whatever buttons OpenEMR shows.
  const possibleAccept = [
    'button:has-text("Authorize")',
    'button:has-text("Allow")',
    'input[value="Authorize"]',
    'input[value="Allow"]',
    'input[value="Submit"]',
    'button:has-text("Continue")',
    'button:has-text("Submit")',
  ]
  // Patient-picker support — OpenEMR's /oauth2/default/smart/patient-select page renders
  // one <button class="patient-btn" data-patient-id="<uuid>"> per patient and a sibling
  // hidden form posting to /smart/patient-select-confirm. We click Maria G.'s button
  // (UUID hard-coded from the demo seed; first button as fallback).
  const MARIA_G_UUID = '11111111-1111-4111-8111-111111111111'
  let pickerDone = false
  async function pickPatientIfAsked() {
    if (pickerDone) return false
    if (!page.url().includes('smart/patient-select')) return false
    if (page.url().includes('patient-select-confirm')) return false
    // Drive the form directly via page.evaluate. Pick Maria G. by UUID,
    // populate the hidden input, submit the form. Wrap the submit in
    // setTimeout(0) so the evaluate returns BEFORE navigation tears down
    // the execution context.
    console.log('[probe] picking patient via direct form submit')
    const submitted = await page
      .evaluate((uuid) => {
        const input = document.getElementById('patient_id')
        const form = document.getElementById('patientForm')
        if (input == null || form == null) return false
        input.value = uuid
        // Defer the submit so this evaluate call resolves first.
        setTimeout(() => form.submit(), 0)
        return true
      }, MARIA_G_UUID)
      .catch((e) => {
        console.log('[probe] picker eval err', e?.message ?? e)
        return false
      })
    if (!submitted) return false
    pickerDone = true
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
    return true
  }
  for (let attempt = 0; attempt < 12 && !authCode; attempt++) {
    if (await pickPatientIfAsked()) {
      await page.waitForTimeout(800)
      // Don't `continue` — fall through to the consent click in case the
      // patient submit lands on /scope-authorize-confirm.
    }
    let clicked = false
    for (const sel of possibleAccept) {
      const loc = page.locator(sel).first()
      if (await loc.count()) {
        await loc.click({ force: true }).catch(() => {})
        await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {})
        clicked = true
        break
      }
    }
    if (!clicked) await page.waitForTimeout(700)
    if (!authCode) await dumpPage(`loop-${attempt}`)
  }
} catch (err) {
  pageError = err
}

await browser.close()

if (!authCode) {
  console.error('[probe] failed to capture auth code', pageError ?? '')
  console.error('[probe] HINT: OpenEMR may have an additional consent screen this script does not click. Inspect manually.')
  process.exit(2)
}

console.log('[probe] auth code captured; exchanging for token')

// ── Token exchange ──────────────────────────────────────────────────────────
const tokenRes = await fetch(`${OPENEMR_BASE}/oauth2/default/token`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    grant_type: 'authorization_code',
    code: authCode,
    redirect_uri: REDIRECT_URI,
    client_id: CLIENT_ID,
    code_verifier: codeVerifier,
  }),
})
if (!tokenRes.ok) {
  const errBody = await tokenRes.text()
  console.error('[probe] token exchange failed', tokenRes.status, errBody)
  process.exit(3)
}
const tokenJson = await tokenRes.json()
const accessToken = tokenJson.access_token
const patientId = tokenJson.patient
const safeTokenJson = { ...tokenJson, access_token: '[REDACTED]', refresh_token: tokenJson.refresh_token ? '[REDACTED]' : undefined, id_token: tokenJson.id_token ? '[REDACTED]' : undefined }
console.log('[probe] token response (redacted):', JSON.stringify(safeTokenJson, null, 2))
console.log('[probe] patient context =', patientId)

if (!accessToken) {
  console.error('[probe] no access_token in response', tokenJson)
  process.exit(4)
}
if (!patientId) {
  console.warn('[probe] no patient context in token response — using launch context fallback')
}

// ── Probe runner ────────────────────────────────────────────────────────────
// OpenEMR's FHIR layer establishes a session via Set-Cookie on the first
// authenticated request. We capture and replay that cookie so subsequent
// requests don't re-establish session each call.
let apiCookie = null
async function fhirGet(path) {
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    Accept: 'application/fhir+json',
  }
  if (apiCookie != null) headers['Cookie'] = apiCookie
  const res = await fetch(`${FHIR_BASE}${path}`, { headers })
  const setCookie = res.headers.get('set-cookie')
  if (setCookie != null) {
    const m = /apiOpenEMR=[^;]+/.exec(setCookie)
    if (m && apiCookie == null) {
      apiCookie = m[0]
      console.log('[probe] captured apiOpenEMR cookie for follow-up requests')
    }
  }
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text)
  } catch {
    // leave as text
  }
  return {
    status: res.status,
    headers: Object.fromEntries(res.headers.entries()),
    body: json ?? text,
  }
}

// Fall back to Maria G.'s known UUID from the demo seed if the token
// response didn't carry a `patient` claim — OpenEMR's flow doesn't
// always include it as a top-level claim.
const MARIA_G_UUID_FALLBACK = '11111111-1111-4111-8111-111111111111'
const pid = patientId || MARIA_G_UUID_FALLBACK
console.log('[probe] running probes for patient =', pid)

// Diagnostic: introspect the token to see scopes, aud, sub, patient.
try {
  const introspectRes = await fetch(`${OPENEMR_BASE}/oauth2/default/introspect`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Bearer ${accessToken}`,
    },
    body: new URLSearchParams({ token: accessToken, client_id: CLIENT_ID }),
  })
  const introspectText = await introspectRes.text()
  console.log('[probe] introspection result:', introspectRes.status)
  console.log(introspectText)
} catch (err) {
  console.log('[probe] introspection failed:', err?.message ?? err)
}

const results = {}

console.log('[probe] sanity probes (metadata, Patient/{id}, /Person)…')
results.metadata = await fhirGet(`/metadata`)
results.patientById = await fhirGet(`/Patient/${pid}`)
results.personById = await fhirGet(`/Person/a1ac0051-f4d5-40c9-9c78-d0024bfcc809`)

console.log('[probe] running Phase 0 medication probe…')
results.medicationRequest = await fhirGet(`/MedicationRequest?patient=${encodeURIComponent(pid)}`)

console.log('[probe] running CareTeam _include probe…')
results.careTeamPlain = await fhirGet(`/CareTeam?patient=${encodeURIComponent(pid)}`)
results.careTeamInclude = await fhirGet(
  `/CareTeam?patient=${encodeURIComponent(pid)}&_include=CareTeam:participant`,
)
// Surrogate: Maria G. has no CareTeam, so the include result is empty either
// way. Use MedicationRequest:requester as a surrogate to learn whether OpenEMR
// honors `_include` at all on this server.
results.medRequestPlain = await fhirGet(`/MedicationRequest?patient=${encodeURIComponent(pid)}`)
results.medRequestIncludeRequester = await fhirGet(
  `/MedicationRequest?patient=${encodeURIComponent(pid)}&_include=MedicationRequest:requester`,
)

console.log('[probe] running status-filter probe…')
results.allergyPlain = await fhirGet(`/AllergyIntolerance?patient=${encodeURIComponent(pid)}`)
results.allergyFiltered = await fhirGet(
  `/AllergyIntolerance?patient=${encodeURIComponent(pid)}&clinical-status=active`,
)

const out = {
  capturedAt: new Date().toISOString(),
  patientId: pid,
  results,
}

const outPath = resolve(projectRoot, 'agentdocs/probe-results/probe.json')
writeFileSync(outPath, JSON.stringify(out, null, 2))
console.log(`[probe] wrote ${outPath}`)
