# Patient Dashboard Migration — Defense

> Wk2 Surprise Challenge: port the OpenEMR patient dashboard to a modern
> framework while leaving the PHP backend untouched. This document is
> the framework-choice defense, in part fulfilling the assignment's
> "explain why you chose your framework, what you gained, and what
> tradeoffs came with that choice."

## Summary

I rebuilt the OpenEMR patient summary as a **standalone Vite + React 19
+ TypeScript single-page app** that authenticates via SMART-on-FHIR
v2.2.0 and consumes OpenEMR's FHIR R4 API as a read-only data layer.
The new app lives at `openemr/dashboard-modern/`. The legacy PHP UI at
`interface/patient_file/summary/demographics.php` is unchanged and
keeps working — both can be run side by side.

Feature parity:
- SMART-on-FHIR login (EHR-launch primary, standalone-launch fallback,
  PKCE public client, sessionStorage token storage, discovery-driven
  logout)
- Persistent patient header (name, DOB, age, sex, MRN, active status)
- Five clinical cards: Allergies (NKDA-aware), Problem List,
  Medications, Prescriptions, Care Team
- Sixth section: Lab Results — most recent 10 `Observation`s with
  H/L/HH/LL abnormal interpretation badges

## Framework choice — Vite + React 19 + TypeScript strict

> **The brief:** "The best is going to be something that's easiest for
> you to reliably code in and support and implement and also shows
> future proofing."

| Layer | Choice |
|---|---|
| Build tool | Vite 8 |
| UI | React 19 + TypeScript strict + `noUncheckedIndexedAccess` |
| SMART/OAuth | `fhirclient` v2 (SMART Health IT) |
| FHIR types | `@types/fhir/r4` |
| Validation | Zod schemas at the FHIR boundary |
| Server-state cache | TanStack Query v5 |
| Routing | React Router v6 |
| Styling | Tailwind CSS v4 + shadcn/ui copies |
| Tests | Vitest + RTL + MSW v2 + Playwright |

### Why this stack wins

1. **Canonical SMART-on-FHIR pattern.** OpenEMR explicitly supports
   EHR-launch + standalone-launch + PKCE for public clients and ships
   a built-in SMART app card UI
   (`templates/patient/card/smart_launch.html.twig`). `fhirclient`'s
   `FHIR.oauth2.authorize()` consumes those launch params natively —
   ~30 LoC of OAuth code, no Auth.js provider config, no Node BFF.
2. **Static deployable.** `npm run build` produces a folder of static
   assets that can be served from any CDN. There is no Node server to
   deploy and pay for.
3. **Type-rigorous end-to-end.** TypeScript strict +
   `noUncheckedIndexedAccess` + `@types/fhir/r4` + Zod gives compile-
   time and runtime guarantees. Healthcare has many similarly-shaped
   strings (UUIDs, MRNs, NPIs, codes) and our types prevent the entire
   class of "wrong ID passed in the wrong slot" bugs.
4. **Strangler-fig fit.** A separate static SPA running on a different
   origin than the legacy PHP UI is the cleanest possible coexistence
   pattern. Nothing breaks if we shut it off; the legacy UI stays
   available for any feature we haven't ported yet.
5. **Agent-friendly parallel work.** Strict file-ownership zones plus
   a frozen view-model contract (`src/models/dashboard.ts`) let four
   subagents (Teams A/B/C/D) implement SMART auth, cards 1–3, cards
   4–6, and the test harness in parallel without colliding. The whole
   build landed in three commits over roughly 90 minutes of agent
   wall time.

### Alternatives ruled out

| Stack | Reason rejected |
|---|---|
| **Keep PHP/Twig/Smarty** | Defeats the assignment ("port the dashboard to a modern framework"). The legacy stack also doesn't compose cleanly with TypeScript-aware tooling, runtime schema validation, or modern test ergonomics. |
| **Next.js 15 (App Router) + Auth.js + Node BFF** | Strong runner-up — earlier drafts of this plan picked it. Adds a Node runtime + BFF complexity that isn't required for a SMART public client; the OAuth flow ends up more bespoke than `fhirclient`'s built-in authorize/ready. **Deferred to Wk3** as the production-hardening path (see "Wk3 hardening" below). |
| **Remix / React Router 7** | Comparable to Next.js. Adds a server runtime we don't need for a read-only consumer. |
| **SvelteKit** | Smaller training corpus; smaller FHIR/SMART JS ecosystem; harder for agents to write reliably. |
| **Nuxt 3 (Vue)** | Smaller agent familiarity than React for SMART work. |
| **Angular standalone** | Heavier framework; slower agent velocity for a one-week sprint. |
| **Phoenix LiveView (Elixir)** | Sparse healthcare community; smaller training corpus. |
| **Django + HTMX / FastAPI + HTMX** | Project already has a Python sidecar; a second Python web stack blurs architecture. |
| **Rails + Hotwire** | Lower agent reliability for this kind of work. |
| **Blazor / .NET** | New runtime/toolchain not aligned with the rest of the repo. |

## What we gained

- **Type safety end-to-end.** PHP plus Smarty gives you stringly typed
  templates and untyped arrays passed across multiple layers.
  TypeScript with `strict` and `noUncheckedIndexedAccess` makes
  argument-transposition and "missing field" bugs compile errors.
  Pairing this with `@types/fhir/r4` means every read of
  `patient.identifier[0].value` is type-checked; pairing it with Zod
  means malformed FHIR responses fail loudly instead of producing
  garbled UI.
- **Runtime FHIR validation.** Every response from the OpenEMR FHIR
  layer is parsed through a Zod schema before any view-model adapter
  sees it. Schemas use `.passthrough()` so unknown fields don't fail,
  but the fields we depend on are checked. If OpenEMR ever changes a
  shape, the failure surfaces at the boundary with a clear error, not
  three layers deep in a render.
- **Canonical SMART pattern.** The `fhirclient` library does PKCE,
  state, nonce, code exchange, refresh, and `client.request()` with
  bearer-attached. Logout is RP-Initiated via the OIDC config's
  `end_session_endpoint`. Token revocation is wired conditionally on
  `revocation_endpoint` (this OpenEMR doesn't advertise one — the
  flow degrades gracefully).
- **Read-only by enforcement, not convention.** A Playwright contract
  test (`tests/contracts/no-mutation.spec.ts`) intercepts every
  request the SPA makes and fails the build if any non-`GET` lands on
  `/apis/default/`. The whitelist for OAuth POSTs (token, optional
  revocation) is read from OIDC discovery at test setup so it's
  self-correcting. Plant-and-revert evidence captured under
  `dashboard-modern/agentdocs/regression-dryrun/`.
- **Agent-friendly parallel work.** Master plan §6 carved the source
  tree into four non-overlapping zones. Teams A/B/C/D each got a
  briefing template (master plan §12) with their files, hard rules,
  and out-of-scope list. The total parallel implementation time was
  roughly 90 minutes of agent wall clock for ~5,500 lines of new code.
- **Strangler-fig coexistence.** The new SPA runs on
  `http://localhost:5173`; the legacy UI continues at
  `http://localhost:8300`. Either surface can be torn down or re-
  deployed without affecting the other. Nothing in the SPA touches
  any PHP file.

## Tradeoffs

- **Public-client tokens in `sessionStorage`.** `fhirclient` defaults
  to `sessionStorage`, which keeps tokens scoped to the tab and
  cleared on close — but XSS could exfiltrate them. Acceptable per
  SMART v2.2.0 + RFC 7636 (PKCE) for a development/demo SPA; **not**
  acceptable for a high-value production deployment. Wk3 hardening
  path below addresses this.
- **CORS dependency.** OpenEMR has to allow the SPA origin. Pre-flight
  verified `Access-Control-Allow-Origin: http://localhost:5173` is
  echoed, so this is a non-issue today. If a future OpenEMR upgrade
  tightens CORS, the dev-only Vite proxy fallback in `vite.config.ts`
  is documented and ready (commented out).
- **Two-language repo.** PHP for OpenEMR core, Python for the AI
  sidecar, TypeScript for the dashboard. Multi-language is normal in
  2026; the cost paid is CI matrix complexity. Mitigated by keeping
  the SPA's tooling self-contained inside `openemr/dashboard-modern/`.
- **No SSR.** A static SPA boots after JS loads. For a clinician-
  facing dashboard inside an EHR session this is irrelevant; for a
  patient-portal scenario where SEO mattered we'd add SSR via Next.js
  (also Wk3).
- **Deferred Wk3 hardening.** Public client + sessionStorage is the
  canonical SMART pattern but not the secure-by-default production
  pattern. See "Wk3 hardening path" below.

## Phase 0 medication-parity spike outcome

OpenEMR's FHIR `MedicationRequest` resource emits both legacy
`lists`-row medications (problem-list "Medications" panel, default
SQL `intent='plan'`) and formal `prescriptions`-row entries (default
SQL `intent='order'`). Source: `src/Services/PrescriptionService.php`
SQL UNION at lines 91–261; mapping at
`src/Services/FHIR/FhirMedicationRequestService.php:496–505`.

Result: **FHIR-only split possible via the `intent` field.** Team B's
Medications card filters `intent === 'plan'`; Team C's Prescriptions
card filters `intent === 'order'`. No Standard REST fallback was
needed. The conditional AgDR-0085 stays unfiled. Caveat documented:
`prescriptions.request_intent` and `lists_medication.request_intent`
can override the SQL defaults; for Maria G.'s seed data those columns
are unset, so defaults hold. Full report:
`dashboard-modern/MEDICATION_PARITY_SPIKE.md`.

## W0 query probe outcomes

Two probes were defined in the master plan for early evidence-
gathering:

1. **CareTeam `_include=CareTeam:participant`** — does OpenEMR's FHIR
   server populate Practitioner resources in the bundle when asked?
2. **Server-side `clinical-status=active` filter on
   AllergyIntolerance / Condition** — silently honored, silently
   ignored, or rejected?

Both probes were **deferred to W-A's first session**. The probe
driver at `dashboard-modern/scripts/probe.mjs` successfully drives the
PKCE auth code flow through OpenEMR's login screen and stalls at
`/oauth2/default/smart/patient-select` — the headless click-through
on that picker was more reverse-engineering than W0's budget allowed.

The defaults that were locked regardless of probe outcome are the
load-bearing implementation:
- **Adapter-side status filtering is canonical** (AgDR-0087). Even if
  a future probe shows server-side filters work, the client-side
  filter stays the source of truth — it's the defense against the
  documented OpenEMR pattern of silently ignoring unknown search
  parameters.
- **Per-participant Practitioner follow-up reads default** (master
  plan §5 W-C). Parallelism cap of 3. `_include` is filed under
  AgDR-0086 only after a confirmed live probe. Until then, all
  CareTeam Practitioner names are resolved by per-participant reads,
  with backoff on missing IDs.

Full report: `dashboard-modern/FHIR_QUERY_PROBES.md`.

## Security posture

- **PKCE S256.** Code challenge/verifier on every auth code request.
- **`Patient.rs`, not `Patient.r`.** Read+search scope (search is
  required for our by-patient queries). Common typo, fixed up front.
- **No bearer token in URLs, logs, or telemetry.** `redact()` strips
  `access_token`, `refresh_token`, `id_token`, `Authorization`, plus
  PHI keys (`name`, `birthDate`, `mrn`, `ssn`, etc.) from any object
  before it crosses a logging boundary.
- **Discovery-driven logout.** `end_session_endpoint` is read from
  `/oauth2/default/.well-known/openid-configuration`. Never hard-
  coded. `revocation_endpoint` is conditional — this OpenEMR doesn't
  advertise one, and `logout.ts` skips the revocation step gracefully.
- **Read-only mutation contract.** Playwright contract test fails the
  build on any non-`GET` to `/apis/default/`. Whitelist
  (`/oauth2/default/token` + optional `revocation_endpoint`) is
  discovered at test setup so it's automatically correct for any
  deployment.
- **Strict CSP-friendly** (no inline scripts, no `dangerouslySetInnerHTML`,
  no third-party CDN scripts).
- **Self-signed cert handled.** Pre-flight verified `https://localhost:9300`
  serves a working cert; Playwright bypasses with `ignoreHTTPSErrors`.

## How to run it (stranger-reproducer — 15 minutes)

1. **Start OpenEMR Docker stack.**
   ```bash
   cd openemr/docker/development-easy
   docker compose up --detach --wait
   ```
   App at `https://localhost:9300/` (admin/pass). Trust the self-
   signed cert in your browser once.

2. **(One-time) register the SMART app.** Already registered for this
   dev environment — `client_id` is in
   `openemr/dashboard-modern/.env.local` (gitignored).
   To re-register, follow `openemr/dashboard-modern/README.md`
   "Register the SMART app" — the curl flow takes ~30 seconds.

3. **Boot the SPA.**
   ```bash
   cd openemr/dashboard-modern
   npm install        # ~3 minutes; postinstall writes public/mockServiceWorker.js
   npm run dev        # serves http://localhost:5173/
   ```

4. **Launch via SMART card.** Browse to
   `https://localhost:9300/interface/patient_file/summary/demographics.php?set_pid=9001`
   (login admin/pass), scroll to the SMART app card, click
   "Launch" on the registered dashboard.

5. **Confirm the dashboard.** OAuth redirects you to
   `http://localhost:5173/index.html?code=...` → fhirclient completes
   the exchange → app navigates to `/dashboard` showing Maria G.'s
   header + 6 cards (Allergies, Problem List, Medications,
   Prescriptions, Care Team, Lab Results).

6. **Verify everything passes.**
   ```bash
   npm run typecheck && npm run lint && npm run test && npm run build
   npx playwright test
   ```

   Expected: 128 vitest tests pass across 11 files; 5 Playwright tests
   pass (2 skipped — opt-in via `PW_WITH_SMART_SESSION=1` and
   `PW_USE_MSW=1`).

## Wk3 hardening path

If we move this from a demo SPA to a production deployment, the
shape of the change is:

1. **Switch to Next.js 15 (App Router) + Node BFF.** Routes proxy
   `/api/fhir/*` from the SPA's same-origin to OpenEMR. The SPA stops
   talking to OpenEMR directly; CORS becomes a non-issue.
2. **Confidential client.** Re-register the SMART app with a client
   secret. Move the secret to a server-side environment variable;
   the BFF holds it.
3. **Token-encrypted httpOnly cookie.** The BFF receives the access
   token at the `/index.html` callback, encrypts it, and stores it in
   an httpOnly secure cookie. The SPA never sees the bearer.
4. **Server-side rate limiting + audit log.** All FHIR calls go
   through the BFF; we log read access at the per-resource level
   (HIPAA audit trail).
5. **CSP enforced via headers, not just policy.** BFF emits
   `Content-Security-Policy: script-src 'self'; ...`.

The current SPA is a clean foundation for that migration: the view-
model contract (`src/models/dashboard.ts`), the Zod boundary, the
adapter layer, and every UI component are server-runtime-agnostic.
Only `fhirclient` calls and the auth module would change shape.

## Parity gaps (known)

- The SPA does not yet implement the Encounter history fallback
  for the 6th section (`AgDR-0083` documented it, but Lab Results was
  workable on Maria G., so the fallback didn't trigger).
- The medication conflict chip (`Duplicate Rx`) detects same-drug
  presence in both Medications and Prescriptions cards by lowercased
  drug-name match. A more precise implementation would compare
  RxNorm codes; deferred to Wk3.
- No medication-list editing or note-writing — the SPA is strictly
  read-only by mutation contract (AgDR-0084). Parity is by viewing,
  not editing.

## What "Done" looks like (assignment checklist)

- [x] Authentication via OAuth2/OpenID Connect — SMART-on-FHIR v2.2.0
      with PKCE; EHR-launch + standalone-launch.
- [x] Patient header — name, DOB, sex, MRN, active status — sourced
      from FHIR `Patient`.
- [x] Allergies — `AllergyIntolerance` with NKDA-aware rendering.
- [x] Problem List — `Condition?category=problem-list-item` filtered
      to `clinicalStatus=active` adapter-side.
- [x] Medications — `MedicationRequest` filtered to `intent=plan`
      (Phase 0 outcome).
- [x] Prescriptions — `MedicationRequest` filtered to `intent=order`,
      with prescriber name resolved via per-participant
      `Practitioner` reads.
- [x] Care Team — `CareTeam` with adapter-side `status=active` filter
      and per-participant Practitioner resolution.
- [x] Sixth section — Lab Results from `Observation?category=laboratory`
      with H/L/HH/LL abnormal interpretation badges.
- [x] Defense documented in this file.
- [x] No PHI in logs or test artifacts.
- [x] Mutation-policy contract test enforces read-only.
- [x] All gates green: typecheck, lint, vitest (128/128), Playwright
      (5 passed, 2 opt-in skipped), production build.
