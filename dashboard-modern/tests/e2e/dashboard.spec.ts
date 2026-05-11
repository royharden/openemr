import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

/**
 * Dashboard smoke tests.
 *
 * Playwright runs with VITE_USE_MSW=0 (no browser service worker) by default
 * so that Vite's lazy chunk resolution is not delayed by service worker
 * lifecycle events in headless Chromium.
 *
 * The fixture-backed test below seeds fhirclient's real sessionStorage shape
 * and routes FHIR calls through Playwright, which gives us a deterministic
 * authenticated dashboard render without relying on a live OpenEMR login.
 *
 * All synthetic data. No PHI. Demo patient is Maria G. (pid 9001).
 */

const PATIENT_ID = 'test-patient-uuid-9001'
const SMART_STATE_KEY = 'pw-smart-state-9001'
const FHIR_BASE_URL = 'https://localhost:9300/apis/default/fhir'

function readFixture(fileName: string): unknown {
  return JSON.parse(
    readFileSync(new URL(`../../src/test/fixtures/${fileName}`, import.meta.url), 'utf8'),
  ) as unknown
}

const patientFixture = readFixture('patient_9001.json')
const allergiesFixture = readFixture('allergies_9001.json')
const conditionsFixture = readFixture('conditions_9001.json')
const medicationRequestsFixture = readFixture('medicationRequests_9001.json')
const careTeamFixture = readFixture('careTeam_9001.json')
const observationsFixture = readFixture('observations_9001.json')

const practitionerFixtures: Record<string, unknown> = {
  'pract-001': readFixture('practitioner_pract-001.json'),
  'pract-002': readFixture('practitioner_pract-002.json'),
  'pract-003': readFixture('practitioner_pract-003.json'),
  'pract-rx-001': readFixture('practitioner_pract-rx-001.json'),
}

async function seedSmartSession(page: Page): Promise<void> {
  await page.addInitScript(({ patientId, stateKey, fhirBaseUrl }) => {
    const scope = [
      'launch',
      'launch/patient',
      'openid',
      'fhirUser',
      'offline_access',
      'patient/Patient.rs',
      'patient/AllergyIntolerance.rs',
      'patient/Condition.rs',
      'patient/MedicationRequest.rs',
      'patient/CareTeam.rs',
      'patient/Observation.rs',
      'patient/Practitioner.rs',
    ].join(' ')

    sessionStorage.setItem('SMART_KEY', JSON.stringify(stateKey))
    sessionStorage.setItem(
      stateKey,
      JSON.stringify({
        key: stateKey,
        serverUrl: fhirBaseUrl,
        clientId: 'playwright-public-client',
        scope,
        tokenUri: 'https://localhost:9300/oauth2/default/token',
        expiresAt: Math.floor(Date.now() / 1000) + 3600,
        tokenResponse: {
          access_token: 'playwright-access-token',
          refresh_token: 'playwright-refresh-token',
          token_type: 'Bearer',
          patient: patientId,
          scope,
        },
      }),
    )
  }, { patientId: PATIENT_ID, stateKey: SMART_STATE_KEY, fhirBaseUrl: FHIR_BASE_URL })
}

async function routeFixtureFhir(page: Page): Promise<void> {
  await page.route('**/apis/default/fhir/Patient/*', async (route) => {
    await route.fulfill({ json: patientFixture })
  })

  await page.route('**/apis/default/fhir/AllergyIntolerance**', async (route) => {
    await route.fulfill({ json: allergiesFixture })
  })

  await page.route('**/apis/default/fhir/Condition**', async (route) => {
    await route.fulfill({ json: conditionsFixture })
  })

  await page.route('**/apis/default/fhir/MedicationRequest**', async (route) => {
    await route.fulfill({ json: medicationRequestsFixture })
  })

  await page.route('**/apis/default/fhir/CareTeam**', async (route) => {
    await route.fulfill({ json: careTeamFixture })
  })

  await page.route('**/apis/default/fhir/Observation**', async (route) => {
    await route.fulfill({ json: observationsFixture })
  })

  await page.route('**/apis/default/fhir/Practitioner/*', async (route) => {
    const id = new URL(route.request().url()).pathname.split('/').pop() ?? ''
    const fixture = practitionerFixtures[id]
    if (fixture == null) {
      await route.fulfill({
        status: 404,
        json: { resourceType: 'OperationOutcome', issue: [{ severity: 'error', code: 'not-found' }] },
      })
      return
    }
    await route.fulfill({ json: fixture })
  })
}

async function setupAuthenticatedFixtureDashboard(page: Page): Promise<void> {
  await seedSmartSession(page)
  await routeFixtureFhir(page)
}

test.describe('Modern Patient Dashboard — smoke', () => {
  test('SPA shell mounts and redirects to /dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10_000 })
  })

  test('SPA renders main content area (dashboard or auth error state)', async ({ page }) => {
    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })

    // The SPA must render a <main> element — either the dashboard grid or an
    // auth-error state. Both are valid for this smoke (full SMART auth is
    // tested in Team A's spec).
    await expect(page.locator('main')).toBeVisible({ timeout: 12_000 })
  })

  test('no uncaught JS errors on mount', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))

    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 12_000 })

    expect(errors, 'no uncaught JS errors on initial mount').toEqual([])
  })

  test('authenticated fixture dashboard renders patient header and all 6 sections', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))
    await setupAuthenticatedFixtureDashboard(page)

    await page.goto('/dashboard')
    await page.waitForSelector('main', { timeout: 12_000 })

    await expect(page.getByRole('heading', { name: 'Maria Elena Garcia' })).toBeVisible()
    await expect(page.getByText('MRN: MRN-9001')).toBeVisible()
    await expect(page.getByText('Active', { exact: true })).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Allergies' })).toBeVisible()
    await expect(page.getByText('Penicillin')).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Problem List' })).toBeVisible()
    await expect(page.getByText('Hypertension')).toBeVisible()
    await expect(page.getByText('Type 2 Diabetes Mellitus')).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Medications' })).toBeVisible()
    await expect(page.getByText('Lisinopril 10 mg', { exact: true })).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Prescriptions' })).toBeVisible()
    await expect(page.getByText('Metformin 500 mg')).toBeVisible()
    await expect(page.getByText('Atorvastatin 20 mg')).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Care Team' })).toBeVisible()
    await expect(page.getByText('Primary Care Team')).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Recent Lab Results' })).toBeVisible()
    await expect(page.getByText('HbA1c')).toBeVisible()
    await expect(page.getByText('Hemoglobin')).toBeVisible()

    expect(errors, 'no uncaught JS errors during fixture dashboard render').toEqual([])
  })

  test('6 section headings visible when SMART session is active', async ({ page }) => {
    // This test is skipped unless PW_WITH_SMART_SESSION=1 is set (live-mode
    // SMART auth provided externally — e.g. by seeding sessionStorage before
    // page load). Without a session the cards render an auth-error state.
    test.skip(
      process.env.PW_WITH_SMART_SESSION !== '1',
      'Requires active SMART session (set PW_WITH_SMART_SESSION=1)',
    )

    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 12_000 })

    const expectedSections = [
      'Allergies',
      'Problem List',
      'Medications',
      'Prescriptions',
      'Care Team',
      'Recent Lab Results',
    ]

    for (const section of expectedSections) {
      await expect(
        page.getByRole('heading', { name: section }),
        `"${section}" section heading should be visible`,
      ).toBeVisible({ timeout: 8_000 })
    }
  })
})

test.describe('Modern Patient Dashboard — mock-mode MSW stub smoke', () => {
  // These tests run in MSW browser mode (PW_USE_MSW=1) where service worker
  // intercepts FHIR calls and serves fixtures. Without a real SMART session,
  // the MSW handlers must also mock the auth/session layer for cards to render.
  test.skip(
    process.env.PW_USE_MSW !== '1',
    'MSW browser mode only — set PW_USE_MSW=1',
  )

  test('all 6 section card headings visible with MSW fixtures', async ({ page }) => {
    await page.goto('/')
    await page.waitForURL(/\/dashboard$/, { timeout: 10_000 })
    await page.waitForSelector('main', { timeout: 15_000 })

    const expectedSections = [
      'Allergies',
      'Problem List',
      'Medications',
      'Prescriptions',
      'Care Team',
      'Recent Lab Results',
    ]

    for (const section of expectedSections) {
      await expect(
        page.getByRole('heading', { name: section }),
        `"${section}" section heading should be visible`,
      ).toBeVisible({ timeout: 8_000 })
    }
  })
})
