# Phase 0 — Medication Parity Spike

Sprint: wk2 — Surprise track
Author: Claude orchestrator
Date: 2026-05-10
Plan: `openemr/planning/Plan_wk2_Claude_Surprise01_2026-05-10_modern-patient-dashboard.md` §8

## Question

Does FHIR `MedicationRequest` carry a discriminator that lets us split
the patient-summary "Medications" panel (legacy `lists`-row entries,
`type='medication'`) from the patient-summary "Prescriptions" panel
(formal `prescriptions`-row entries) — without reaching for the Standard
REST `/api/patient/:pid/medication` endpoint?

If yes → both cards can be driven from a single FHIR query, with the
adapter splitting in JS.

If no → the Medications card uses Standard REST as a documented gap;
file AgDR-0085.

## Verdict

**FHIR-only split is POSSIBLE via the `intent` field.** No Standard REST
fallback needed. AgDR-0085 stays conditional/unfiled.

## Evidence (code-derived)

`openemr/src/Services/PrescriptionService.php` returns a UNION of two
sources, with each branch defaulting `intent` to a different value:

```sql
-- PrescriptionService.php:91–261 (skeleton)
SELECT ..., 'prescriptions' AS source_table,
       COALESCE(prescriptions.request_intent, 'order') AS intent,
       COALESCE(prescriptions.request_intent_title, 'Order') AS intent_title
FROM prescriptions
UNION
SELECT ..., 'lists' AS source_table,
       IF(lists_medication.request_intent IS NULL, 'plan', lists_medication.request_intent) AS intent,
       IF(lists_medication.request_intent_title IS NULL, 'Plan', lists_medication.request_intent_title) AS intent_title
FROM lists JOIN lists_medication
WHERE lists.type = 'medication'
  AND lists_medication.prescription_id IS NULL  -- excludes lists rows that mirror a prescription
```

`openemr/src/Services/FHIR/FhirMedicationRequestService.php:496–505`
forwards the SQL `intent` straight into `MedicationRequest.intent` via
`FHIRMedicationIntentEnum`:

```php
public function populateIntent(FHIRMedicationRequest $medRequestResource, array $dataRecord)
{
    $intent = FHIRMedicationIntentEnum::tryFrom($dataRecord['intent'] ?? 'plan');
    if ($intent != null) {
        $medRequestResource->setIntent($intent->value);
    } else {
        $medRequestResource->setIntent(FHIRMedicationIntentEnum::PLAN);
    }
}
```

| Source | SQL default | FHIR `intent` | Maps to UI card |
|---|---|---|---|
| `prescriptions` table | `'order'` | `order` | **Prescriptions card** |
| `lists` (with `type='medication'`, no linked prescription) | `'plan'` | `plan` | **Medications card** |

The `source_table` column exists in PHP but is **not** propagated to the
FHIR resource — the discriminator we ride on is `intent`.

A `lists`-row whose `lists_medication.prescription_id` is set is excluded
from the UNION (line 260 of PrescriptionService.php), so we are not at
risk of double-counting a single therapy across both cards.

## Caveat (limit of the discriminator)

The defaults can be overridden by SQL columns
`prescriptions.request_intent` and `lists_medication.request_intent`. In
principle, a manually authored prescription row could set
`request_intent='plan'`, or a manual lists-row could set
`request_intent='order'`. In Maria G.'s seed data
(`agent/copilot-api/demo/seed_demo_patient.sql`) those columns are not
set, so defaults hold. The migration defense doc records this as a
known data-quality dependency.

## Live-probe status (deferred)

The Phase 0 spike's *step 2* was to confirm the verdict against a live
`MedicationRequest?patient=<uuid>` response. The probe driver
(`scripts/probe.mjs`) successfully completes the SMART OAuth dance
through OpenEMR's login screen and reaches the patient-picker page at
`/oauth2/default/smart/patient-select`. Selecting a patient
programmatically requires more reverse-engineering of that page than
the W0 budget allows. The verdict above is decisive on its own — the
live curl will be re-run during Workstream A's first session, when an
EHR-launched bearer token (with patient context already bound) is
naturally available.

## Decision

- **Workstream B's `getActiveMedications`** queries
  `MedicationRequest?patient=<id>`, the adapter filters
  `intent === 'plan'` (and `status === 'active'`).
- **Workstream C's `getActivePrescriptions`** queries the same path; the
  adapter filters `intent === 'order'`.
- **Conflict chip:** when the same drug code appears in both lists, the
  cards surface a conflict marker — same logic as the legacy lists-vs-
  prescriptions UI in `interface/patient_file/summary/demographics.php`.
- **AgDR-0085** stays conditional/unfiled. Only file if we discover
  `intent`-default overrides in production data.

## Files inspected

- `openemr/src/Services/PrescriptionService.php` (473 lines)
- `openemr/src/Services/FHIR/FhirMedicationRequestService.php` (596 lines)
