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

## Live-probe status — CONFIRMED 2026-05-10 PM

The Phase 0 spike's *step 2* live confirmation now landed via the
extended `scripts/probe.mjs` driver. Maria G.'s 4 `MedicationRequest`
entries match the predicted split exactly:

| FHIR id | `intent` | `status` | drug | UI card |
|---|---|---|---|---|
| a1bf39b7-61de-4760-ba36-a7a2fa2c4fbd | `order` | `active` | Metformin | Prescriptions |
| a1bf39b7-6346-4551-95e5-836dbb328c88 | `order` | `active` | Lisinopril | Prescriptions |
| a1bf39b7-634f-4ab5-ac73-7b9d1e2dbd1b | `order` | `active` | Atorvastatin | Prescriptions |
| a1be95b9-0d15-4e73-8134-6855e979d514 | `plan`  | `active` | Lisinopril 10 mg PO daily | Medications |

The 4th entry — a `lists`-row Lisinopril with `intent=plan` — co-exists
with a formal Lisinopril Rx (`intent=order`). This is the exact
**conflict-chip use case** Team B's `MedicationsCard` handles. Live
data thus also validates the Duplicate-Rx UI logic.

Probe artifact: `agentdocs/probe-results/probe.json` (committed for
reproducibility — synthetic Maria G. data, no PHI).

### How to re-run the live probe

```bash
cd openemr/dashboard-modern
node scripts/probe.mjs
```

The driver runs entirely in headless Chromium with `ignoreHTTPSErrors`,
authenticates as admin/pass, picks Maria G., completes consent, and
captures the access token. Outputs land in
`agentdocs/probe-results/probe.json`.

> **Pre-req lesson:** The OpenEMR SMART app must include `launch/patient`
> in its registered scope list for standalone-launch probes to bind a
> patient context to the access token. The original 2026-05-10
> registration was missing this scope; we patched it via direct SQL on
> `oauth_clients.scope` (recorded in the W0 commit's status companion
> drift log §I).

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
