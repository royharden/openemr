import { describe, it, expect, vi, beforeEach } from 'vitest'
import { adaptPrescriptions } from '@/models/adapters/prescriptions'
import { adaptCareTeam } from '@/models/adapters/careTeam'
import { adaptLabs } from '@/models/adapters/labs'
import { CareTeamSchema } from '@/fhir/schemas/careTeam'
import { ObservationSchema } from '@/fhir/schemas/observation'
import { PractitionerSchema, extractPractitionerName } from '@/fhir/schemas/practitioner'
import { MedicationRequestSchema } from '@/fhir/schemas/medicationRequest'
import { FhirBundleSchema } from '@/fhir/schemas/bundle'

import careTeamFixtureRaw from '@/test/fixtures/careTeam_9001.json'
import observationsFixtureRaw from '@/test/fixtures/observations_9001.json'
import medicationRequestsFixtureRaw from '@/test/fixtures/medicationRequests_9001.json'
import practitioner1Raw from '@/test/fixtures/practitioner_pract-001.json'
import practitioner2Raw from '@/test/fixtures/practitioner_pract-002.json'
import practitionerRx1Raw from '@/test/fixtures/practitioner_pract-rx-001.json'

// ─── Helper ───────────────────────────────────────────────────────────────────

function extractBundleResources<T>(
  bundleJson: unknown,
  schema: { safeParse: (x: unknown) => { success: true; data: T } | { success: false } },
): T[] {
  const bundle = FhirBundleSchema.parse(bundleJson)
  return (bundle.entry ?? [])
    .map((e) => e.resource)
    .map((raw) => schema.safeParse(raw))
    .filter((r): r is { success: true; data: T } => r.success)
    .map((r) => r.data)
}

// ─── Prescriptions adapter ────────────────────────────────────────────────────

describe('prescriptions adapter', () => {
  const allResources = extractBundleResources(medicationRequestsFixtureRaw, MedicationRequestSchema)

  it('happy path — returns only intent=order AND status=active entries', () => {
    const rxs = adaptPrescriptions(allResources, new Map())
    expect(rxs).toHaveLength(1)
    expect(rxs[0]!.id).toBe('medreq-9001-rx-lisinopril')
    expect(rxs[0]!.status).toBe('active')
  })

  it('inactive-filter regression — intent=plan meds are NOT in prescriptions output', () => {
    const rxs = adaptPrescriptions(allResources, new Map())
    const ids = rxs.map((r) => r.id)
    expect(ids).not.toContain('medreq-9001-lisinopril')
    expect(ids).not.toContain('medreq-9001-metformin')
    expect(ids).not.toContain('medreq-9001-atorvastatin')
  })

  it('completed-filter regression — completed entries are NOT in prescriptions output', () => {
    const rxs = adaptPrescriptions(allResources, new Map())
    const ids = rxs.map((r) => r.id)
    expect(ids).not.toContain('medreq-9001-amoxicillin-completed')
  })

  it('prescriber name resolved from practitionerNamesById map', () => {
    const nameMap = new Map([['pract-rx-001', 'Dr. Robert Williams']])
    const resource = MedicationRequestSchema.parse({
      resourceType: 'MedicationRequest',
      id: 'rx-with-pract',
      status: 'active',
      intent: 'order',
      medicationCodeableConcept: { text: 'TestDrug 5 mg' },
      requester: { reference: 'Practitioner/pract-rx-001' },
    })
    const rxs = adaptPrescriptions([resource], nameMap)
    expect(rxs[0]!.prescriberName).toBe('Dr. Robert Williams')
  })

  it('falls back to requester.display when no practitioner map entry', () => {
    const resource = MedicationRequestSchema.parse({
      resourceType: 'MedicationRequest',
      id: 'rx-display',
      status: 'active',
      intent: 'order',
      medicationCodeableConcept: { text: 'TestDrug 5 mg' },
      requester: { display: 'Dr. Smith' },
    })
    const rxs = adaptPrescriptions([resource], new Map())
    expect(rxs[0]!.prescriberName).toBe('Dr. Smith')
  })

  it('empty list — returns empty array', () => {
    expect(adaptPrescriptions([], new Map())).toHaveLength(0)
  })

  it('malformed resource (no medication info) — drug falls back to "Unknown medication"', () => {
    const resource = MedicationRequestSchema.parse({
      resourceType: 'MedicationRequest',
      id: 'bare-rx',
      status: 'active',
      intent: 'order',
    })
    const rxs = adaptPrescriptions([resource], new Map())
    expect(rxs[0]!.drug).toBe('Unknown medication')
  })
})

// ─── CareTeam adapter ─────────────────────────────────────────────────────────

describe('careTeam adapter', () => {
  const allResources = extractBundleResources(careTeamFixtureRaw, CareTeamSchema)

  it('happy path — fixture has 2 resources (active + inactive)', () => {
    expect(allResources).toHaveLength(2)
  })

  it('status-filter regression (LOAD-BEARING) — inactive team is NOT in adapter output', () => {
    const teams = adaptCareTeam(allResources, new Map())
    expect(teams).toHaveLength(1)
    const ids = teams.map((t) => t.id)
    expect(ids).not.toContain('ct-002')
    expect(ids).toContain('ct-001')
  })

  it('active team has correct name and members', () => {
    const teams = adaptCareTeam(allResources, new Map())
    const team = teams[0]!
    expect(team.name).toBe('Primary Care Team')
    expect(team.status).toBe('active')
    expect(team.members).toHaveLength(2)
  })

  it('member name resolved from practitionerNamesById map', () => {
    const nameMap = new Map([
      ['pract-001', 'Dr. Sarah Johnson'],
      ['pract-002', 'Nurse Patricia Lopez'],
    ])
    const teams = adaptCareTeam(allResources, nameMap)
    const members = teams[0]!.members
    expect(members[0]!.name).toBe('Dr. Sarah Johnson')
    expect(members[1]!.name).toBe('Nurse Patricia Lopez')
  })

  it('member falls back to display string when not in name map', () => {
    const teams = adaptCareTeam(allResources, new Map())
    const members = teams[0]!.members
    expect(members[0]!.name).toBe('Dr. Sarah Johnson')
  })

  it('empty list — returns empty array', () => {
    expect(adaptCareTeam([], new Map())).toHaveLength(0)
  })
})

// ─── Labs (Observation) adapter ───────────────────────────────────────────────

describe('labs adapter', () => {
  const allResources = extractBundleResources(observationsFixtureRaw, ObservationSchema)

  it('happy path — fixture has 11 resources', () => {
    expect(allResources).toHaveLength(11)
  })

  it('limit to n=10 — adapter returns max 10 entries', () => {
    const labs = adaptLabs(allResources, 10)
    expect(labs).toHaveLength(10)
  })

  it('sort newest first — first result is obs-001 (2026-05-10)', () => {
    const labs = adaptLabs(allResources, 10)
    expect(labs[0]!.id).toBe('obs-001')
  })

  it('11th item excluded — obs-011 (oldest, 2026-03-01) not in top 10', () => {
    const labs = adaptLabs(allResources, 10)
    const ids = labs.map((l) => l.id)
    expect(ids).not.toContain('obs-011')
  })

  it('abnormal interpretation — obs-001 (high potassium) marked as "high"', () => {
    const labs = adaptLabs(allResources, 10)
    const potassium = labs.find((l) => l.id === 'obs-001')
    expect(potassium).toBeDefined()
    expect(potassium!.interpretation).toBe('high')
    expect(potassium!.value).toBe('5.9 mmol/L')
  })

  it('normal interpretation — obs-002 (HbA1c) marked as "normal"', () => {
    const labs = adaptLabs(allResources, 10)
    const hba1c = labs.find((l) => l.id === 'obs-002')
    expect(hba1c).toBeDefined()
    expect(hba1c!.interpretation).toBe('normal')
  })

  it('low interpretation — obs-003 (hemoglobin) marked as "low"', () => {
    const labs = adaptLabs(allResources, 10)
    const hgb = labs.find((l) => l.id === 'obs-003')
    expect(hgb).toBeDefined()
    expect(hgb!.interpretation).toBe('low')
  })

  it('reference range formatted correctly for obs-001', () => {
    const labs = adaptLabs(allResources, 10)
    const potassium = labs.find((l) => l.id === 'obs-001')
    expect(potassium!.referenceRange).toBe('3.5–5.1 mmol/L')
  })

  it('limit=1 — returns only most recent', () => {
    const labs = adaptLabs(allResources, 1)
    expect(labs).toHaveLength(1)
    expect(labs[0]!.id).toBe('obs-001')
  })

  it('empty list — returns empty array', () => {
    expect(adaptLabs([], 10)).toHaveLength(0)
  })
})

// ─── Practitioner schema + name extraction ────────────────────────────────────

describe('practitioner schema and name extraction', () => {
  it('parses practitioner fixture without throwing', () => {
    expect(() => PractitionerSchema.parse(practitioner1Raw)).not.toThrow()
  })

  it('extractPractitionerName — returns formatted name from fixture', () => {
    const pract = PractitionerSchema.parse(practitioner1Raw)
    expect(extractPractitionerName(pract)).toBe('Dr. Sarah Johnson')
  })

  it('extractPractitionerName — falls back to text field if present', () => {
    const pract = PractitionerSchema.parse({
      resourceType: 'Practitioner',
      id: 'p-text',
      name: [{ text: 'Dr. Text Only' }],
    })
    expect(extractPractitionerName(pract)).toBe('Dr. Text Only')
  })

  it('extractPractitionerName — returns null when no name', () => {
    const pract = PractitionerSchema.parse({ resourceType: 'Practitioner', id: 'p-noname' })
    expect(extractPractitionerName(pract)).toBeNull()
  })

  it('extracts name from practitioner 2 fixture (nurse)', () => {
    const pract = PractitionerSchema.parse(practitioner2Raw)
    expect(extractPractitionerName(pract)).toBe('RN Patricia Lopez')
  })

  it('extracts name from prescriber fixture', () => {
    const pract = PractitionerSchema.parse(practitionerRx1Raw)
    expect(extractPractitionerName(pract)).toBe('Dr. Robert Williams')
  })
})

// ─── CareTeam schema passthrough ─────────────────────────────────────────────

describe('CareTeam schema passthrough', () => {
  it('allows unknown fields without throwing', () => {
    expect(() =>
      CareTeamSchema.parse({ resourceType: 'CareTeam', id: 'ct-x', _extra: true }),
    ).not.toThrow()
  })

  it('accepts all status values from fixture', () => {
    const resources = extractBundleResources(careTeamFixtureRaw, CareTeamSchema)
    const statuses = resources.map((r) => r.status)
    expect(statuses).toContain('active')
    expect(statuses).toContain('inactive')
  })
})

// ─── Observation schema passthrough ──────────────────────────────────────────

describe('Observation schema passthrough', () => {
  it('allows unknown fields without throwing', () => {
    expect(() =>
      ObservationSchema.parse({ resourceType: 'Observation', id: 'obs-x', _extra: true }),
    ).not.toThrow()
  })

  it('parses all 11 observation fixtures successfully', () => {
    const resources = extractBundleResources(observationsFixtureRaw, ObservationSchema)
    expect(resources).toHaveLength(11)
  })
})

// ─── Query function signatures ─────────────────────────────────────────────────

describe('Team C query function signatures', () => {
  beforeEach(() => {
    vi.mock('@/fhir/client', () => ({
      fhirGet: vi.fn(),
      getClient: vi.fn(),
    }))
  })

  it('getActivePrescriptions is a function', async () => {
    const { getActivePrescriptions } = await import('@/fhir/queries/prescriptions')
    expect(typeof getActivePrescriptions).toBe('function')
  })

  it('getActiveCareTeam is a function', async () => {
    const { getActiveCareTeam } = await import('@/fhir/queries/careTeam')
    expect(typeof getActiveCareTeam).toBe('function')
  })

  it('getRecentLabResults is a function', async () => {
    const { getRecentLabResults } = await import('@/fhir/queries/observations')
    expect(typeof getRecentLabResults).toBe('function')
  })
})

// ─── Per-participant Practitioner follow-up read path (LOAD-BEARING) ──────────
// Proves adapter works with a pre-resolved name map populated by the query's
// per-participant reads, NOT by an _include bundle.

describe('per-participant Practitioner follow-up read path', () => {
  it('adapter receives names via Map (not _include) — resolves correctly', () => {
    const resources = extractBundleResources(careTeamFixtureRaw, CareTeamSchema)

    // Simulate what the query does: per-participant reads → Map
    const practitioner1 = PractitionerSchema.parse(practitioner1Raw)
    const practitioner2 = PractitionerSchema.parse(practitioner2Raw)

    const nameMap = new Map<string, string>([
      ['pract-001', extractPractitionerName(practitioner1) ?? ''],
      ['pract-002', extractPractitionerName(practitioner2) ?? ''],
    ])

    const teams = adaptCareTeam(resources, nameMap)
    const activeTeam = teams.find((t) => t.id === 'ct-001')
    expect(activeTeam).toBeDefined()

    const member0 = activeTeam!.members[0]!
    const member1 = activeTeam!.members[1]!
    expect(member0.name).toBe('Dr. Sarah Johnson')
    expect(member1.name).toBe('RN Patricia Lopez')
  })

  it('adapter with EMPTY name map (simulates bundle without _include) — falls back to display', () => {
    const resources = extractBundleResources(careTeamFixtureRaw, CareTeamSchema)
    const teams = adaptCareTeam(resources, new Map())

    const activeTeam = teams.find((t) => t.id === 'ct-001')
    expect(activeTeam).toBeDefined()

    // Without name map, should fall back to member.display from FHIR
    const member0 = activeTeam!.members[0]!
    expect(member0.name).toBe('Dr. Sarah Johnson')
  })
})
