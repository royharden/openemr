# W0 — FHIR Query Probes

Sprint: wk2 — Surprise track
Author: Claude orchestrator
Date: 2026-05-10
Plan: `openemr/planning/Plan_wk2_Claude_Surprise01_2026-05-10_modern-patient-dashboard.md`
§5 Workstream 0 (probes 2 + 3) and §3 conditional AgDR-0086.

## Summary

| Probe | Purpose | Outcome |
|---|---|---|
| Discovery probes | Validate SMART + OIDC discovery URLs and capabilities | ✅ verified during pre-flight (status companion §M) |
| OAuth dance | Reach the OpenEMR `/token` endpoint with an authorization code | ✅ working end-to-end up to patient-select |
| `MedicationRequest` shape (Phase 0) | Confirm `intent` discriminator | ⚠ **deferred** — verdict already locked from code analysis (see `MEDICATION_PARITY_SPIKE.md`) |
| `CareTeam` `_include=CareTeam:participant` | Does OpenEMR honor it? | ⚠ **deferred** — defaulting to per-participant follow-up reads |
| `AllergyIntolerance` `&clinical-status=active` | Server-side filter honored? | ⚠ **deferred** — adapter-side filter is canonical regardless |

## Why "deferred"

The probe driver (`scripts/probe.mjs`) successfully drives the SMART
auth_code + PKCE flow through OpenEMR's login form, but stalls on the
patient-select page at `/oauth2/default/smart/patient-select`. That
page is rendered by OpenEMR's `OAuth2KeyConfig` controller and shows a
search-and-pick UI rather than a flat input field; clicking through it
programmatically requires more reverse-engineering than the W0 budget
allows. Workstream A owns the SMART auth implementation and will be
naturally driving an EHR-launched flow (where a `patient` context is
bound by OpenEMR before the SPA receives the token), so live probes
attach there for free.

The defaults below are **safe regardless of probe outcome**, so the
build is unblocked.

## Defaults locked in (no live probe needed)

### CareTeam member resolution

- **Default:** per-participant Practitioner follow-up reads, parallelism
  cap of 3.
- **Conditional optimization:** if Workstream A's first session
  observes `_include=CareTeam:participant` does in fact populate the
  bundle entries with Practitioner resources, file AgDR-0086 and switch
  to the include-based path. Until then, the per-participant path is
  the canonical implementation.

### Status filtering

- **Canonical default:** every adapter that consumes a status-bearing
  FHIR resource filters in JS:
    - Allergies → `clinicalStatus.coding[*].code === 'active'`
    - Conditions → `clinicalStatus.coding[*].code === 'active'`
    - CareTeam → `status === 'active'`
    - MedicationRequest (both cards) → `status === 'active'`
- **Server-side `clinical-status=active` query parameter** is **not**
  added — even if a future probe shows OpenEMR honors it. The
  adapter-side filter is the load-bearing implementation; treating the
  server-side filter as an optimization-only signal is the lesson from
  past regressions where servers silently ignored unknown search
  parameters.

## Probe driver — usable artifact

`scripts/probe.mjs` is checked in as a reusable diagnostic. It:

1. Loads `.env.local` and constructs the SMART authorize URL with PKCE
   (S256 code_challenge, fresh state).
2. Drives a Playwright headless Chromium through the login screen
   (admin/pass).
3. Reaches `/oauth2/default/smart/patient-select` (currently the
   stopping point) — Workstream A extends from here.
4. Captures the auth code via a `localhost:5173/**` route fulfiller.
5. Exchanges code for token at `/oauth2/default/token`.
6. Runs the three probe queries and writes results to
   `agentdocs/probe-results/probe.json`.

To run later (after extending the patient-select handler):

```bash
cd openemr/dashboard-modern
node scripts/probe.mjs
```

## Discovery findings (already verified during pre-flight)

These are reproduced from status companion §M for Workstream A's
convenience; W-A does not need to re-verify.

| Capability | Verified value |
|---|---|
| SMART config URL | `${VITE_OPENEMR_FHIR_BASE_URL}/.well-known/smart-configuration` |
| OIDC config URL | `${VITE_OPENEMR_BASE_URL}/oauth2/default/.well-known/openid-configuration` |
| `capabilities` includes | `launch-ehr`, `launch-standalone`, `client-public`, `permission-offline`, `context-ehr-patient` |
| PKCE | `S256` supported |
| `MedicationStatement` exposed? | No — only `MedicationRequest` and `Medication` (anti-pattern #20 confirmed) |
| `revocation_endpoint` | **NOT advertised** — logout flow degrades gracefully (clear sessionStorage + redirect to `end_session_endpoint`) |

## Implications for Workstream A

- Wire `FHIR.oauth2.authorize()` for both EHR launch and standalone
  launch.
- For the standalone case, scope must include `launch/patient` so
  OpenEMR's patient-select page renders. See `scripts/probe.mjs` for
  one driver pattern.
- `logout.ts` must NOT include a revocation step that fails when the
  endpoint is missing — wrap in a `cfg.revocation_endpoint != null`
  check before issuing the POST.
- Re-run `scripts/probe.mjs` (or fold into a Playwright test under
  `tests/e2e/`) after `getActiveCareTeam` is implemented to file
  AgDR-0086 if and only if `_include` is honored.
