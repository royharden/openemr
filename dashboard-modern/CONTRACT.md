# Locked-Signature Contract — Workstream 0 Freeze

This document is the **boundary** between the orchestrator's scaffold
and the four parallel teammates (A/B/C/D). Anything in here is locked
unless an AgDR records the change.

Frozen at: 2026-05-10 (Workstream 0 commit on branch
`wk2-surprise-modern-dashboard`).

## What's locked

### `src/models/dashboard.ts`

The view-model types defined in `src/models/dashboard.ts`. Components
consume these. Adapters produce them. Adding a field requires a
sentence in the status companion §C/§D; changing or removing a field
requires an AgDR.

In particular:

- `PatientHeaderData` — what the patient header renders.
- `AllergiesView` (incl. `nkda` flag), `AllergyDisplay`.
- `ProblemDisplay`.
- `MedicationDisplay` with `origin: 'list' | 'prescription' | 'unknown'`
  (the Phase 0 spike outcome lives in this discriminator).
- `PrescriptionDisplay`.
- `CareTeamDisplay`, `CareTeamMember`.
- `LabResultDisplay`, `LabInterpretation`.
- `EncounterDisplay` (only used if Lab section falls back per
  AgDR-0083).
- `LoadState<T>` envelope.

### `src/fhir/queries/*.ts` signatures

| Function | Signature | Owner |
|---|---|---|
| `getPatient` | `(patientId: string) => Promise<PatientHeaderData>` | W-B |
| `getActiveAllergies` | `(patientId: string) => Promise<AllergiesView>` | W-B |
| `getActiveProblems` | `(patientId: string) => Promise<ReadonlyArray<ProblemDisplay>>` | W-B |
| `getActiveMedications` | `(patientId: string) => Promise<ReadonlyArray<MedicationDisplay>>` | W-B |
| `getActivePrescriptions` | `(patientId: string) => Promise<ReadonlyArray<PrescriptionDisplay>>` | W-C |
| `getActiveCareTeam` | `(patientId: string) => Promise<ReadonlyArray<CareTeamDisplay>>` | W-C |
| `getRecentLabResults` | `(patientId: string, n?: number) => Promise<ReadonlyArray<LabResultDisplay>>` | W-C |

Bodies throw `Error('… not implemented — Workstream X')`. Replacing
the body is allowed; changing the signature is not.

### `src/models/adapters/*.ts` signatures

| Function | Signature | Owner |
|---|---|---|
| `adaptPatientHeader` | `(resource: Patient) => PatientHeaderData` | W-B |
| `adaptAllergies` | `(resources: ReadonlyArray<AllergyIntolerance>) => AllergiesView` | W-B |
| `adaptProblems` | `(resources: ReadonlyArray<Condition>) => ReadonlyArray<ProblemDisplay>` | W-B |
| `adaptMedications` | `(resources: ReadonlyArray<MedicationRequest>) => ReadonlyArray<MedicationDisplay>` | W-B |
| `adaptPrescriptions` | `(resources: ReadonlyArray<MedicationRequest>, practitionerNamesById: ReadonlyMap<string,string>) => ReadonlyArray<PrescriptionDisplay>` | W-C |
| `adaptCareTeam` | `(resources: ReadonlyArray<CareTeam>, practitionerNamesById: ReadonlyMap<string,string>) => ReadonlyArray<CareTeamDisplay>` | W-C |
| `adaptLabs` | `(resources: ReadonlyArray<Observation>, n: number) => ReadonlyArray<LabResultDisplay>` | W-C |

Status filtering is the **adapter's job**, not the query's. This is the
canonical defense against OpenEMR's silently-ignored server-side
status filters.

### `src/fhir/schemas/*.ts`

Each schema is `z.object({ resourceType: z.literal(...), id: z.string() }).passthrough()`.
Workstreams B/C tighten as needed; the **outer Zod parse step**
remains the boundary between FHIR responses and adapter input.

### `src/auth/*.ts` skeletons

Workstream A implements bodies. Public surface locked:

- `smartClient.ts` exports `getSmartConfig()`, `authorize()`, `ready()`.
- `session.ts` exports `Session` type, `EMPTY_SESSION`, `getSession()`.
- `redact.ts` exports `redact<T>(input)` — already implemented in W0.
- `oidcConfig.ts` exports `getOidcConfig()`,
  `getEndSessionEndpoint()`, `getRevocationEndpoint()` (returns
  `null` on this OpenEMR per §M discovery), `getTokenEndpoint()`.
- `logout.ts` exports `logout(options?)`.

### Environment surface

| Var | Locked at |
|---|---|
| `VITE_OPENEMR_BASE_URL` | `https://localhost:9300` |
| `VITE_OPENEMR_FHIR_BASE_URL` | `${VITE_OPENEMR_BASE_URL}/apis/default/fhir` |
| `VITE_SMART_CLIENT_ID` | from registration (`.env.local` only — not committed) |
| `VITE_DEFAULT_SCOPES` | scope string from §K of the status companion |
| `VITE_USE_MSW` | `0` or `1` |

## What's NOT locked

- Adapter bodies, query bodies, schema field-level shapes, MSW handler
  bodies, fixture content, component innards, route element content.
  Teams own these.
- Tailwind utility classes inside components (subject to design
  iteration).
- Styles in `src/styles/tailwind.css` (W0 wrote a thin global; teams
  can tune).

## Promotion path

When a team needs to change a locked surface:

1. Open a status-companion §C/§D entry describing the change.
2. The orchestrator either accepts and updates `dashboard.ts` /
   signatures and bumps an AgDR, or pushes back. No team edits
   `dashboard.ts` or query/adapter signatures unilaterally.
