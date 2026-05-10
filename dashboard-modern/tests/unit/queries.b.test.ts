import { describe, it, expect, vi, beforeEach } from 'vitest'
import { adaptPatientHeader } from '@/models/adapters/patientHeader'
import { adaptAllergies } from '@/models/adapters/allergies'
import { adaptProblems } from '@/models/adapters/problems'
import { adaptMedications } from '@/models/adapters/medications'
import { PatientSchema } from '@/fhir/schemas/patient'
import { AllergyIntoleranceSchema } from '@/fhir/schemas/allergyIntolerance'
import { ConditionSchema } from '@/fhir/schemas/condition'
import { MedicationRequestSchema } from '@/fhir/schemas/medicationRequest'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'

import patientFixtureRaw from '@/test/fixtures/patient_9001.json'
import allergiesFixtureRaw from '@/test/fixtures/allergies_9001.json'
import conditionsFixtureRaw from '@/test/fixtures/conditions_9001.json'
import medicationRequestsFixtureRaw from '@/test/fixtures/medicationRequests_9001.json'

// ─── Helper: extract resources from a fixture bundle ──────────────────────────

function extractBundleResources<T>(
  bundleJson: unknown,
  schema: { safeParse: (x: unknown) => { success: true; data: T } | { success: false } },
): T[] {
  const bundle = FhirBundleSchema.parse(bundleJson)
  return (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => schema.safeParse(raw))
    .filter(
      (r): r is { success: true; data: T } => r.success,
    )
    .map((r) => r.data)
}

// ─── Patient ──────────────────────────────────────────────────────────────────

describe('patientHeader adapter', () => {
  it('happy path — parses Maria G. fixture and produces correct view model', () => {
    const resource = PatientSchema.parse(patientFixtureRaw)
    const header = adaptPatientHeader(resource)

    expect(header.id).toBe('patient-9001')
    expect(header.fullName).toBe('Maria Elena Garcia')
    expect(header.dateOfBirth).toBe('1985-03-22')
    expect(header.ageYears).toBeGreaterThan(30)
    expect(header.sex).toBe('female')
    expect(header.mrn).toBe('MRN-9001')
    expect(header.active).toBe(true)
  })

  it('returns "unknown" sex when gender is absent', () => {
    const resource = PatientSchema.parse({ resourceType: 'Patient', id: 'no-gender' })
    expect(adaptPatientHeader(resource).sex).toBe('unknown')
  })

  it('falls back to id as MRN when no identifier present', () => {
    const resource = PatientSchema.parse({ resourceType: 'Patient', id: 'test-id' })
    expect(adaptPatientHeader(resource).mrn).toBe('test-id')
  })

  it('returns "Unknown Patient" when no name present', () => {
    const resource = PatientSchema.parse({ resourceType: 'Patient', id: 'test-id' })
    expect(adaptPatientHeader(resource).fullName).toBe('Unknown Patient')
  })

  it('malformed birthDate — ageYears falls back to 0', () => {
    const resource = PatientSchema.parse({ resourceType: 'Patient', id: 'x' })
    expect(adaptPatientHeader(resource).ageYears).toBe(0)
  })
})

// ─── Allergies ────────────────────────────────────────────────────────────────

describe('allergies adapter', () => {
  it('happy path — returns only the active allergy from fixture', () => {
    const resources = extractBundleResources(allergiesFixtureRaw, AllergyIntoleranceSchema)
    expect(resources).toHaveLength(2)

    const view = adaptAllergies(resources)
    expect(view.nkda).toBe(false)
    expect(view.items).toHaveLength(1)
    expect(view.items[0]!.substance).toBe('Penicillin')
    expect(view.items[0]!.criticality).toBe('high')
    expect(view.items[0]!.reactions).toContain('Skin rash')
  })

  it('inactive-filter regression — resolved allergy is NOT in output', () => {
    const resources = extractBundleResources(allergiesFixtureRaw, AllergyIntoleranceSchema)
    const view = adaptAllergies(resources)
    const ids = view.items.map((a) => a.id)
    expect(ids).not.toContain('allergy-9001-sulfa-resolved')
  })

  it('empty list — returns nkda=false and empty items', () => {
    const view = adaptAllergies([])
    expect(view.nkda).toBe(false)
    expect(view.items).toHaveLength(0)
  })

  it('NKDA — single SNOMED 716186003 entry sets nkda=true', () => {
    const nkdaResource = AllergyIntoleranceSchema.parse({
      resourceType: 'AllergyIntolerance',
      id: 'nkda-entry',
      clinicalStatus: { coding: [{ code: 'active' }] },
      code: {
        coding: [{ system: 'http://snomed.info/sct', code: '716186003', display: 'No known drug allergy' }],
        text: 'NKDA',
      },
    })
    const view = adaptAllergies([nkdaResource])
    expect(view.nkda).toBe(true)
    expect(view.items).toHaveLength(0)
  })

  it('malformed resource (no code) — substance falls back to "Unknown substance"', () => {
    const resource = AllergyIntoleranceSchema.parse({
      resourceType: 'AllergyIntolerance',
      id: 'bare',
      clinicalStatus: { coding: [{ code: 'active' }] },
    })
    const view = adaptAllergies([resource])
    expect(view.items[0]!.substance).toBe('Unknown substance')
  })
})

// ─── Conditions (Problem List) ────────────────────────────────────────────────

describe('problems adapter', () => {
  it('happy path — returns only the 3 active conditions', () => {
    const resources = extractBundleResources(conditionsFixtureRaw, ConditionSchema)
    expect(resources).toHaveLength(4)

    const problems = adaptProblems(resources)
    expect(problems).toHaveLength(3)
  })

  it('inactive-filter regression — resolved UTI condition is NOT in output', () => {
    const resources = extractBundleResources(conditionsFixtureRaw, ConditionSchema)
    const problems = adaptProblems(resources)
    const ids = problems.map((p) => p.id)
    expect(ids).not.toContain('condition-9001-uti-resolved')
  })

  it('displays correct data for hypertension entry', () => {
    const resources = extractBundleResources(conditionsFixtureRaw, ConditionSchema)
    const htn = adaptProblems(resources).find((p) => p.id === 'condition-9001-htn')
    expect(htn).toBeDefined()
    expect(htn!.display).toBe('Hypertension')
    expect(htn!.code).toBe('I10')
    expect(htn!.clinicalStatus).toBe('active')
    expect(htn!.onset).toBe('2018-04-01')
  })

  it('empty list — returns empty array', () => {
    expect(adaptProblems([])).toHaveLength(0)
  })

  it('malformed resource (no code) — display falls back to "Unknown problem"', () => {
    const resource = ConditionSchema.parse({
      resourceType: 'Condition',
      id: 'bare',
      clinicalStatus: { coding: [{ code: 'active' }] },
    })
    const problems = adaptProblems([resource])
    expect(problems[0]!.display).toBe('Unknown problem')
  })
})

// ─── Medications ──────────────────────────────────────────────────────────────

describe('medications adapter', () => {
  it('happy path — returns only intent=plan AND status=active entries', () => {
    const resources = extractBundleResources(medicationRequestsFixtureRaw, MedicationRequestSchema)
    expect(resources).toHaveLength(5)

    const meds = adaptMedications(resources)
    expect(meds).toHaveLength(3)
    expect(meds.every((m) => m.origin === 'list')).toBe(true)
    expect(meds.every((m) => m.status === 'active')).toBe(true)
  })

  it('inactive-filter regression — completed intent=plan med is NOT in output', () => {
    const resources = extractBundleResources(medicationRequestsFixtureRaw, MedicationRequestSchema)
    const meds = adaptMedications(resources)
    const ids = meds.map((m) => m.id)
    expect(ids).not.toContain('medreq-9001-amoxicillin-completed')
  })

  it('prescriptions-split regression — intent=order entry is NOT in medications output', () => {
    const resources = extractBundleResources(medicationRequestsFixtureRaw, MedicationRequestSchema)
    const meds = adaptMedications(resources)
    const ids = meds.map((m) => m.id)
    expect(ids).not.toContain('medreq-9001-rx-lisinopril')
  })

  it('produces correct drug and dose for lisinopril entry', () => {
    const resources = extractBundleResources(medicationRequestsFixtureRaw, MedicationRequestSchema)
    const lisi = adaptMedications(resources).find((m) => m.id === 'medreq-9001-lisinopril')
    expect(lisi).toBeDefined()
    expect(lisi!.drug).toBe('Lisinopril 10 mg')
    expect(lisi!.route).toBe('Oral')
    expect(lisi!.effectiveDate).toBe('2021-03-15')
    expect(lisi!.origin).toBe('list')
  })

  it('empty list — returns empty array', () => {
    expect(adaptMedications([])).toHaveLength(0)
  })

  it('malformed resource (no medication info) — drug falls back to "Unknown medication"', () => {
    const resource = MedicationRequestSchema.parse({
      resourceType: 'MedicationRequest',
      id: 'bare',
      status: 'active',
      intent: 'plan',
    })
    const meds = adaptMedications([resource])
    expect(meds[0]!.drug).toBe('Unknown medication')
  })
})

// ─── Zod schema pass-through ──────────────────────────────────────────────────

describe('Zod schema passthrough', () => {
  it('PatientSchema allows unknown fields without throwing', () => {
    expect(() =>
      PatientSchema.parse({ resourceType: 'Patient', id: 'x', unknownField: 'y' }),
    ).not.toThrow()
  })

  it('AllergyIntoleranceSchema allows unknown fields', () => {
    expect(() =>
      AllergyIntoleranceSchema.parse({
        resourceType: 'AllergyIntolerance',
        id: 'x',
        xCustomExtension: 'foo',
      }),
    ).not.toThrow()
  })

  it('ConditionSchema allows unknown fields', () => {
    expect(() =>
      ConditionSchema.parse({ resourceType: 'Condition', id: 'x', _extra: true }),
    ).not.toThrow()
  })

  it('MedicationRequestSchema allows unknown fields', () => {
    expect(() =>
      MedicationRequestSchema.parse({ resourceType: 'MedicationRequest', id: 'x', extra: 1 }),
    ).not.toThrow()
  })
})

// ─── Ensure queries are callable (signatures) ─────────────────────────────────

describe('query function signatures', () => {
  beforeEach(() => {
    // fhirGet is Team A's code; mock it so queries don't throw "not implemented"
    vi.mock('@/fhir/client', () => ({
      fhirGet: vi.fn(),
      getClient: vi.fn(),
    }))
  })

  it('getPatient is a function', async () => {
    const { getPatient } = await import('@/fhir/queries/patient')
    expect(typeof getPatient).toBe('function')
  })

  it('getActiveAllergies is a function', async () => {
    const { getActiveAllergies } = await import('@/fhir/queries/allergies')
    expect(typeof getActiveAllergies).toBe('function')
  })

  it('getActiveProblems is a function', async () => {
    const { getActiveProblems } = await import('@/fhir/queries/conditions')
    expect(typeof getActiveProblems).toBe('function')
  })

  it('getActiveMedications is a function', async () => {
    const { getActiveMedications } = await import('@/fhir/queries/medications')
    expect(typeof getActiveMedications).toBe('function')
  })
})
