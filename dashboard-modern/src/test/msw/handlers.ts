import { http, HttpResponse } from 'msw'
import patientFixture from '../fixtures/patient_9001.json'
import allergiesFixture from '../fixtures/allergies_9001.json'
import conditionsFixture from '../fixtures/conditions_9001.json'
import medicationRequestsFixture from '../fixtures/medicationRequests_9001.json'
import careTeamFixture from '../fixtures/careTeam_9001.json'
import observationsFixture from '../fixtures/observations_9001.json'
import practitioner1Fixture from '../fixtures/practitioner_pract-001.json'
import practitioner2Fixture from '../fixtures/practitioner_pract-002.json'
import practitioner3Fixture from '../fixtures/practitioner_pract-003.json'
import practitionerRx1Fixture from '../fixtures/practitioner_pract-rx-001.json'

/**
 * MSW request handlers.
 *
 * Auth handlers (Team A):
 * - FHIR-side SMART configuration discovery
 * - OAuth-side OIDC configuration discovery
 * - Token endpoint (code exchange + refresh)
 *
 * FHIR resource handlers (Teams B/C stubs — bodies owned by B/C):
 * - Patient, AllergyIntolerance, Condition, MedicationRequest
 * - CareTeam, Observation, Practitioner
 *
 * Workstream D owns server.ts wiring.
 * All URLs match path wildcards so they work regardless of base URL.
 */

// ─── Auth / discovery ────────────────────────────────────────────────────────

const SMART_CONFIG_RESPONSE = {
  issuer: 'https://localhost:9300/oauth2/default',
  jwks_uri: 'https://localhost:9300/oauth2/default/jwks',
  authorization_endpoint: 'https://localhost:9300/oauth2/default/authorize',
  token_endpoint: 'https://localhost:9300/oauth2/default/token',
  token_endpoint_auth_methods_supported: ['client_secret_basic', 'private_key_jwt'],
  grant_types_supported: ['authorization_code', 'client_credentials', 'refresh_token'],
  registration_endpoint: 'https://localhost:9300/oauth2/default/registration',
  scopes_supported: [
    'openid', 'fhirUser', 'offline_access', 'launch', 'launch/patient',
    'patient/Patient.rs', 'patient/AllergyIntolerance.rs', 'patient/Condition.rs',
    'patient/MedicationRequest.rs', 'patient/CareTeam.rs', 'patient/Observation.rs',
    'patient/Practitioner.rs', 'patient/Encounter.rs',
  ],
  response_types_supported: ['code'],
  capabilities: [
    'launch-ehr', 'launch-standalone', 'client-public',
    'permission-offline', 'context-ehr-patient',
    'sso-openid-connect', 'authorize-post',
  ],
  code_challenge_methods_supported: ['S256'],
}

const OIDC_CONFIG_RESPONSE = {
  issuer: 'https://localhost:9300/oauth2/default',
  authorization_endpoint: 'https://localhost:9300/oauth2/default/authorize',
  token_endpoint: 'https://localhost:9300/oauth2/default/token',
  jwks_uri: 'https://localhost:9300/oauth2/default/jwks',
  introspection_endpoint: 'https://localhost:9300/oauth2/default/introspect',
  end_session_endpoint: 'https://localhost:9300/oauth2/default/logout',
  // revocation_endpoint NOT advertised — matches live OpenEMR (status §M)
  response_types_supported: ['code'],
  subject_types_supported: ['public'],
  id_token_signing_alg_values_supported: ['RS256'],
  scopes_supported: ['openid', 'fhirUser', 'offline_access'],
  token_endpoint_auth_methods_supported: ['client_secret_basic', 'private_key_jwt'],
  claims_supported: ['sub', 'iss', 'fhirUser'],
}

export const MOCK_TOKEN_RESPONSE = {
  access_token: 'mock-access-token-patient-9001',
  token_type: 'Bearer',
  expires_in: 3600,
  scope: 'launch openid fhirUser patient/Patient.rs patient/AllergyIntolerance.rs patient/Condition.rs patient/MedicationRequest.rs patient/CareTeam.rs patient/Observation.rs patient/Practitioner.rs',
  id_token: 'mock-id-token',
  refresh_token: 'mock-refresh-token',
  patient: 'test-patient-uuid-9001',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isPatient9001(id: string) {
  return id === 'test-patient-uuid-9001' || id === '9001'
}

const practitionerMap: Record<string, unknown> = {
  'pract-001': practitioner1Fixture,
  'pract-002': practitioner2Fixture,
  'pract-003': practitioner3Fixture,
  'pract-rx-001': practitionerRx1Fixture,
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

export const handlers = [
  http.get('/__msw_smoke', () => HttpResponse.json({ ok: true })),

  // FHIR-side SMART configuration discovery
  http.get('*/apis/default/fhir/.well-known/smart-configuration', () =>
    HttpResponse.json(SMART_CONFIG_RESPONSE),
  ),

  // OAuth-side OIDC configuration discovery
  http.get('*/oauth2/default/.well-known/openid-configuration', () =>
    HttpResponse.json(OIDC_CONFIG_RESPONSE),
  ),

  // Token endpoint
  http.post('*/oauth2/default/token', async ({ request }) => {
    const params = new URLSearchParams(await request.text())
    const grant = params.get('grant_type')

    if (grant === 'authorization_code') {
      if (params.get('code') === 'denied') {
        return HttpResponse.json(
          { error: 'access_denied', error_description: 'User denied consent' },
          { status: 400 },
        )
      }
      return HttpResponse.json(MOCK_TOKEN_RESPONSE)
    }

    if (grant === 'refresh_token') {
      if (params.get('refresh_token') === 'expired-refresh-token') {
        return HttpResponse.json(
          { error: 'invalid_grant', error_description: 'Refresh token expired' },
          { status: 400 },
        )
      }
      return HttpResponse.json({ ...MOCK_TOKEN_RESPONSE, access_token: 'mock-refreshed-access-token' })
    }

    return HttpResponse.json({ error: 'unsupported_grant_type' }, { status: 400 })
  }),

  // ─── FHIR resources — Team B ──────────────────────────────────────────────

  http.get('*/apis/default/fhir/Patient/:id', ({ params }) => {
    if (isPatient9001(params['id'] as string)) return HttpResponse.json(patientFixture)
    return HttpResponse.json(
      { resourceType: 'OperationOutcome', issue: [{ severity: 'error', code: 'not-found' }] },
      { status: 404 },
    )
  }),

  http.get('*/apis/default/fhir/AllergyIntolerance', ({ request }) => {
    const p = new URL(request.url).searchParams.get('patient')
    return HttpResponse.json(
      p != null && isPatient9001(p)
        ? allergiesFixture
        : { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] },
    )
  }),

  http.get('*/apis/default/fhir/Condition', ({ request }) => {
    const p = new URL(request.url).searchParams.get('patient')
    return HttpResponse.json(
      p != null && isPatient9001(p)
        ? conditionsFixture
        : { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] },
    )
  }),

  http.get('*/apis/default/fhir/MedicationRequest', ({ request }) => {
    const p = new URL(request.url).searchParams.get('patient')
    return HttpResponse.json(
      p != null && isPatient9001(p)
        ? medicationRequestsFixture
        : { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] },
    )
  }),

  // ─── FHIR resources — Team C ──────────────────────────────────────────────

  http.get('*/apis/default/fhir/CareTeam', ({ request }) => {
    const p = new URL(request.url).searchParams.get('patient')
    return HttpResponse.json(
      p != null && isPatient9001(p)
        ? careTeamFixture
        : { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] },
    )
  }),

  http.get('*/apis/default/fhir/Observation', ({ request }) => {
    const p = new URL(request.url).searchParams.get('patient')
    return HttpResponse.json(
      p != null && isPatient9001(p)
        ? observationsFixture
        : { resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] },
    )
  }),

  http.get('*/apis/default/fhir/Practitioner/:id', ({ params }) => {
    const fixture = practitionerMap[params['id'] as string]
    if (fixture != null) return HttpResponse.json(fixture)
    return HttpResponse.json(
      { resourceType: 'OperationOutcome', issue: [{ severity: 'error', code: 'not-found' }] },
      { status: 404 },
    )
  }),
]
