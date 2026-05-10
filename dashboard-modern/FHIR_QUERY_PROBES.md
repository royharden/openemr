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
| OAuth dance | Reach the OpenEMR `/token` endpoint with an authorization code | ✅ end-to-end (login → patient-select → consent → token) |
| `MedicationRequest` shape (Phase 0) | Confirm `intent` discriminator | ✅ **CONFIRMED LIVE** — Maria G.'s 4 entries split exactly as predicted (3 `order`, 1 `plan`) |
| `CareTeam` `_include=CareTeam:participant` | Does OpenEMR honor it? | ❌ **DOES NOT WORK** — surrogate test (`MedicationRequest:requester`) shows `_include` *zeroes the result set* on this OpenEMR (4 → 0 entries). AgDR-0086 stays unfiled. |
| `AllergyIntolerance` `&clinical-status=active` | Server-side filter honored? | ❌ **BROKEN** — server-side `clinical-status=active` returns 0 entries despite an active allergy being present; adapter-side filter (AgDR-0087) is now load-bearing with live evidence |

## Live-probe results (2026-05-10 PM)

Probe artifact: `agentdocs/probe-results/probe.json`. The driver
(`scripts/probe.mjs`) authenticates as admin/pass, picks Maria G.
through OpenEMR's `/oauth2/default/smart/patient-select` page, completes
consent, and runs all four queries with the bound access token.

### Phase 0 medication parity — CONFIRMED

`GET /apis/default/fhir/MedicationRequest?patient=<maria-uuid>` returns
4 entries:

| FHIR id | `intent` | `status` | drug |
|---|---|---|---|
| a1bf39b7-61de-4760-ba36-a7a2fa2c4fbd | `order` | `active` | Metformin |
| a1bf39b7-6346-4551-95e5-836dbb328c88 | `order` | `active` | Lisinopril |
| a1bf39b7-634f-4ab5-ac73-7b9d1e2dbd1b | `order` | `active` | Atorvastatin |
| a1be95b9-0d15-4e73-8134-6855e979d514 | `plan`  | `active` | Lisinopril 10 mg PO daily |

The 4th entry (legacy `lists`-row Lisinopril with `intent=plan`) co-
exists with a formal Rx Lisinopril (`intent=order`). This validates
both the Phase 0 verdict AND Team B's Duplicate-Rx conflict-chip logic
in `MedicationsCard`.

### CareTeam `_include` — DOES NOT WORK

Maria G. has no CareTeam records (`?patient=` returns 0 entries), so
the direct `?_include=CareTeam:participant` test was inconclusive. As
a surrogate, we ran:

| Query | Entry count |
|---|---|
| `MedicationRequest?patient=<maria-uuid>` | 4 |
| `MedicationRequest?patient=<maria-uuid>&_include=MedicationRequest:requester` | **0** |

Adding `_include` to a query that otherwise returns 4 entries reduces
it to 0. OpenEMR doesn't ignore `_include` — it actively breaks the
query. This is decisive evidence that `_include=CareTeam:participant`
must NOT be enabled. Per-participant Practitioner follow-up reads
(parallelism cap of 3) is the load-bearing default. **AgDR-0086 stays
unfiled.**

### Server-side status filter — BROKEN

| Query | Entry count |
|---|---|
| `AllergyIntolerance?patient=<maria-uuid>` | 1 (`clinicalStatus.coding[0].code = "active"`) |
| `AllergyIntolerance?patient=<maria-uuid>&clinical-status=active` | **0** |

The server-side `clinical-status=active` filter excludes a record that
*is* active. This is the lesson the master plan §3 reviewer feedback
predicted — and now we have live confirmation. **AgDR-0087 (adapter-
side filtering as canonical default) is no longer "defensive" —
without it, the dashboard would show empty cards on real data.**

## Lessons learned during live-probe development

- **The OpenEMR SMART app must list `launch/patient` in its registered
  scope** for standalone-launch probes to bind a patient context. The
  original 2026-05-10 registration didn't include it; patched via
  direct SQL on `oauth_clients.scope` (logged in status companion §I).
- **OpenEMR's `apiOpenEMR` session cookie** is set on the first
  authenticated FHIR request. The driver replays it on subsequent
  requests so the FHIR server doesn't re-establish session each call.
- **`form.submit()` from `page.evaluate()`** must be deferred via
  `setTimeout(0)` to let the evaluate call resolve before navigation
  destroys the execution context.
- **The full standalone OAuth flow has 4 hops**:
  `/authorize → /provider/login → /smart/patient-select → /smart/patient-select-confirm → /scope-authorize-confirm → /device/code → redirect_uri?code=…`
- **OpenEMR's access token JWT does NOT carry the `patient` claim**
  directly — patient context is stored server-side in `oauth_trusted_user.session_cache.puuid`
  and rehydrated on each FHIR request via the access token's id.

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
