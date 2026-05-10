import { describe, it, expect } from 'vitest'

// Workstream-0 smoke test: every locked-signature query stub exists and
// is exported as a function. This pins the public surface so Workstreams
// B and C can be drafted to a stable contract.

import * as patientQ from '@/fhir/queries/patient'
import * as allergiesQ from '@/fhir/queries/allergies'
import * as conditionsQ from '@/fhir/queries/conditions'
import * as medicationsQ from '@/fhir/queries/medications'
import * as prescriptionsQ from '@/fhir/queries/prescriptions'
import * as careTeamQ from '@/fhir/queries/careTeam'
import * as observationsQ from '@/fhir/queries/observations'

import * as patientHeaderA from '@/models/adapters/patientHeader'
import * as allergiesA from '@/models/adapters/allergies'
import * as problemsA from '@/models/adapters/problems'
import * as medicationsA from '@/models/adapters/medications'
import * as prescriptionsA from '@/models/adapters/prescriptions'
import * as careTeamA from '@/models/adapters/careTeam'
import * as labsA from '@/models/adapters/labs'

import { redact } from '@/auth/redact'

describe('W0 contract surface', () => {
  it('exports every query function', () => {
    expect(typeof patientQ.getPatient).toBe('function')
    expect(typeof allergiesQ.getActiveAllergies).toBe('function')
    expect(typeof conditionsQ.getActiveProblems).toBe('function')
    expect(typeof medicationsQ.getActiveMedications).toBe('function')
    expect(typeof prescriptionsQ.getActivePrescriptions).toBe('function')
    expect(typeof careTeamQ.getActiveCareTeam).toBe('function')
    expect(typeof observationsQ.getRecentLabResults).toBe('function')
  })

  it('exports every adapter function', () => {
    expect(typeof patientHeaderA.adaptPatientHeader).toBe('function')
    expect(typeof allergiesA.adaptAllergies).toBe('function')
    expect(typeof problemsA.adaptProblems).toBe('function')
    expect(typeof medicationsA.adaptMedications).toBe('function')
    expect(typeof prescriptionsA.adaptPrescriptions).toBe('function')
    expect(typeof careTeamA.adaptCareTeam).toBe('function')
    expect(typeof labsA.adaptLabs).toBe('function')
  })

  it('redacts known token + PHI keys', () => {
    const out = redact({
      access_token: 'should-be-hidden',
      name: 'Maria G.',
      benign: 'ok',
      nested: { refresh_token: 'also-hidden', mrn: '12345' },
    })
    expect(out).toEqual({
      access_token: '[REDACTED_TOKEN]',
      name: '[REDACTED_PHI]',
      benign: 'ok',
      nested: { refresh_token: '[REDACTED_TOKEN]', mrn: '[REDACTED_PHI]' },
    })
  })
})
