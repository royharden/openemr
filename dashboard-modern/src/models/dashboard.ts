/**
 * FROZEN dashboard view-model contract.
 *
 * CONTRACT (locked at end of Workstream 0 — 2026-05-10):
 * The shapes in this file are the boundary between FHIR adapters and React
 * components. Teams A/B/C/D consume these types; the orchestrator owns
 * additions. Renames or removals require an AgDR.
 *
 * Components NEVER import raw FHIR resource types. They consume only the view
 * models defined here. Adapters in src/models/adapters/ are the only producers.
 */

// ──────────────────────────────────────────────────────────────────────────────
// Patient header
// ──────────────────────────────────────────────────────────────────────────────

export type Sex = 'male' | 'female' | 'other' | 'unknown'

export type PatientHeaderData = Readonly<{
  id: string
  fullName: string
  dateOfBirth: string // ISO YYYY-MM-DD
  ageYears: number
  sex: Sex
  mrn: string
  active: boolean
}>

// ──────────────────────────────────────────────────────────────────────────────
// Allergies — AllergyIntolerance
// ──────────────────────────────────────────────────────────────────────────────

export type Criticality = 'low' | 'high' | 'unable-to-assess' | 'unknown'

export type AllergyDisplay = Readonly<{
  id: string
  substance: string
  clinicalStatus: 'active' | 'inactive' | 'resolved' | 'unknown'
  verificationStatus: 'unconfirmed' | 'presumed' | 'confirmed' | 'refuted' | 'entered-in-error' | 'unknown'
  criticality: Criticality
  reactions: ReadonlyArray<string>
  recordedDate: string | null // ISO date or null
}>

/**
 * Special view-model: explicit "No Known Drug Allergies" record.
 * The cards layer renders this differently from an empty list.
 */
export type AllergiesView = Readonly<{
  nkda: boolean
  items: ReadonlyArray<AllergyDisplay>
}>

// ──────────────────────────────────────────────────────────────────────────────
// Problem List — Condition (category=problem-list-item, status=active)
// ──────────────────────────────────────────────────────────────────────────────

export type ProblemDisplay = Readonly<{
  id: string
  display: string // code.text or code.coding[0].display
  code: string | null // ICD-10 / SNOMED code text
  codeSystem: string | null
  clinicalStatus: 'active' | 'recurrence' | 'relapse' | 'inactive' | 'remission' | 'resolved' | 'unknown'
  onset: string | null // ISO date
  recordedDate: string | null
}>

// ──────────────────────────────────────────────────────────────────────────────
// Medications + Prescriptions — MedicationRequest, split per Phase 0 spike
// ──────────────────────────────────────────────────────────────────────────────

export type MedicationStatus =
  | 'active'
  | 'on-hold'
  | 'cancelled'
  | 'completed'
  | 'entered-in-error'
  | 'stopped'
  | 'draft'
  | 'unknown'

export type MedicationDisplay = Readonly<{
  id: string
  drug: string
  dose: string | null
  route: string | null
  status: MedicationStatus
  effectiveDate: string | null // ISO
  /**
   * Phase-0 discriminator: 'list' = legacy lists-row medication entry;
   * 'prescription' = formal Rx; 'unknown' = could not split (REST fallback).
   */
  origin: 'list' | 'prescription' | 'unknown'
}>

export type PrescriptionDisplay = Readonly<{
  id: string
  drug: string
  sig: string | null // dosage instruction text
  status: MedicationStatus
  authoredOn: string | null // ISO
  prescriberName: string | null
}>

// ──────────────────────────────────────────────────────────────────────────────
// Care Team
// ──────────────────────────────────────────────────────────────────────────────

export type CareTeamMember = Readonly<{
  id: string
  name: string | null
  role: string | null
  practitionerId: string | null
}>

export type CareTeamDisplay = Readonly<{
  id: string
  name: string | null
  status: 'active' | 'inactive' | 'proposed' | 'suspended' | 'entered-in-error' | 'unknown'
  members: ReadonlyArray<CareTeamMember>
}>

// ──────────────────────────────────────────────────────────────────────────────
// Lab Results — Observation (category=laboratory)
// ──────────────────────────────────────────────────────────────────────────────

export type LabInterpretation = 'normal' | 'high' | 'low' | 'critical-high' | 'critical-low' | 'abnormal' | 'unknown'

export type LabResultDisplay = Readonly<{
  id: string
  display: string // code.coding[0].display or code.text
  value: string | null // formatted "N unit"
  unit: string | null
  referenceRange: string | null // formatted "low–high unit"
  effectiveDateTime: string | null // ISO
  interpretation: LabInterpretation
}>

// ──────────────────────────────────────────────────────────────────────────────
// Encounter (Lab fallback section)
// ──────────────────────────────────────────────────────────────────────────────

export type EncounterDisplay = Readonly<{
  id: string
  type: string | null
  status: string
  start: string | null // ISO
  end: string | null // ISO
  reason: string | null
}>

// ──────────────────────────────────────────────────────────────────────────────
// Top-level dashboard state (consumed by Dashboard.tsx)
// ──────────────────────────────────────────────────────────────────────────────

export type DashboardData = Readonly<{
  header: PatientHeaderData
  allergies: AllergiesView
  problems: ReadonlyArray<ProblemDisplay>
  medications: ReadonlyArray<MedicationDisplay>
  prescriptions: ReadonlyArray<PrescriptionDisplay>
  careTeam: ReadonlyArray<CareTeamDisplay>
  labs: ReadonlyArray<LabResultDisplay>
}>

// ──────────────────────────────────────────────────────────────────────────────
// Async load-state envelope. Cards consume this from TanStack Query.
// ──────────────────────────────────────────────────────────────────────────────

export type LoadState<T> =
  | Readonly<{ status: 'loading' }>
  | Readonly<{ status: 'success'; data: T }>
  | Readonly<{ status: 'empty' }>
  | Readonly<{ status: 'error'; error: Error }>
