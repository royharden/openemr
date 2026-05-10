# OpenEMR Modern Patient Dashboard

A standalone Vite + React 19 + TypeScript SPA that authenticates via
SMART-on-FHIR v2.2.0 and renders a modern patient dashboard for
OpenEMR. Read-only consumer of OpenEMR's existing FHIR R4 API — zero
PHP edits, zero schema changes, zero Docker compose changes.

This is the Wk2 *Surprise Challenge* deliverable. The legacy PHP
dashboard at `interface/patient_file/summary/demographics.php` is
unchanged and still works; this app runs alongside it as a strangler-
fig replacement for one bounded surface.

## Stack

| Layer | Choice |
|---|---|
| Build | Vite 8 |
| UI | React 19 + TypeScript 6 strict + `noUncheckedIndexedAccess` |
| SMART/OAuth | `fhirclient` v2 (SMART Health IT) — `FHIR.oauth2.authorize()` / `ready()` / `client.request()` |
| FHIR types | `@types/fhir/r4` |
| Validation | Zod schemas at the FHIR boundary |
| Server-state | TanStack Query v5 |
| Routing | React Router v6 |
| Styling | Tailwind v4 + shadcn/ui copies |
| Tests | Vitest + RTL + MSW v2 + Playwright |

The defense-of-choice document (`openemr/PATIENT_DASHBOARD_MIGRATION.md`)
is produced by Workstream E.

## Prerequisites

- Node.js 20+ (24.14.1 used during development).
- OpenEMR Docker stack running locally; FHIR endpoint reachable at
  `https://localhost:9300/apis/default/fhir`.
- One-time browser cert-trust click-through against `https://localhost:9300/`
  (the Docker stack uses a self-signed cert).

## Quickstart

```bash
cd openemr/dashboard-modern
cp .env.example .env.local       # paste VITE_SMART_CLIENT_ID
npm install
npm run dev                      # serves http://localhost:5173/
```

`npm run dev` defaults to whatever `VITE_USE_MSW` is in your
`.env.local`. `start:mock` and `start:live` flip it explicitly.

## npm scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server on `:5173`. |
| `npm run start:mock` | Vite dev server with `VITE_USE_MSW=1`. Boots MSW; all FHIR calls are mocked. Offline-friendly. |
| `npm run start:live` | Vite dev server with `VITE_USE_MSW=0`. Requires OpenEMR running. |
| `npm run build` | Type-checks and builds production assets to `dist/`. Two HTML inputs (`index.html` + `launch.html`). |
| `npm run typecheck` | `tsc -b --noEmit` over the project references. |
| `npm run lint` | ESLint over `src/` and `tests/`. |
| `npm run test` | Vitest run (unit + integration via MSW). |
| `npm run test:watch` | Vitest in watch mode. |
| `npm run test:e2e` | Playwright (auto-spawns the dev server in mock mode via `playwright.config.ts` `webServer`). |

## Register the SMART app

> The Wk2 Surprise orchestrator already registered the SMART app on
> 2026-05-10. The `client_id` is recorded in
> `openemr/planning/Plan_wk2_Claude_Surprise01_2026-05-10_modern-patient-dashboard_status.md`
> §K and committed to `.env.local`. **Most readers will not need to
> repeat these steps.**

This walkthrough exists for (a) re-registration / additional apps and
(b) the migration defense doc.

### Option A — RFC 7591 dynamic registration via curl (fastest)

```bash
curl -k -X POST https://localhost:9300/oauth2/default/registration \
  -H 'Content-Type: application/json' \
  --data '{
    "client_name": "OpenEMR Modern Patient Dashboard",
    "redirect_uris": ["http://localhost:5173/index.html"],
    "post_logout_redirect_uris": ["http://localhost:5173/"],
    "initiate_login_uri": "http://localhost:5173/launch.html",
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "scope": "launch openid fhirUser offline_access patient/Patient.rs patient/AllergyIntolerance.rs patient/Condition.rs patient/MedicationRequest.rs patient/CareTeam.rs patient/Observation.rs patient/Practitioner.rs patient/Encounter.rs",
    "application_type": "web"
  }'
```

> ⚠ **Lesson learned 2026-05-10:** Do NOT pass
> `"token_endpoint_auth_method": "none"` in the registration body —
> OpenEMR's dynamic-registration endpoint rejects it with
> `Unsupported token_endpoint_auth_method value : none`. Just omit the
> field; OpenEMR returns the registration with empty `client_secret`
> and `is_confidential=0`, which is the correct public-client outcome.

The response contains `client_id`. Capture it. Newly registered apps
default to `is_enabled = 0`; enable with one SQL statement (this is
what the admin UI does under the hood):

```bash
docker compose -f openemr/docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr -e \
  "UPDATE oauth_clients SET is_enabled = 1 WHERE client_id = '<the_client_id>';"
```

The response also returns a `registration_access_token` and
`registration_client_uri` (RFC 7592). Save both — they let you
GET / PUT / DELETE this client registration later without admin login.

### Option B — Web UI

1. Browse to `https://localhost:9300/interface/smart/register-app.php`
   (admin login).
2. App Name: `OpenEMR Modern Patient Dashboard`. Launch URL:
   `http://localhost:5173/launch.html`. Redirect URI:
   `http://localhost:5173/index.html`. App Type: **Public**.
3. Scopes (paste exactly):
   ```
   launch openid fhirUser
   patient/Patient.rs
   patient/AllergyIntolerance.rs
   patient/Condition.rs
   patient/MedicationRequest.rs
   patient/CareTeam.rs
   patient/Observation.rs
   patient/Practitioner.rs
   ```
4. Submit → copy `client_id`.
5. Administration → System → Clients → enable the new entry.
6. Paste `client_id` into `dashboard-modern/.env.local` as
   `VITE_SMART_CLIENT_ID`.

## Two well-known endpoints — don't conflate them

| Purpose | URL | Used by |
|---|---|---|
| **SMART configuration** (auth endpoints, capabilities, scopes) | `${VITE_OPENEMR_FHIR_BASE_URL}/.well-known/smart-configuration` | `fhirclient` discovers automatically from `iss`. |
| **OIDC configuration** (token, end_session, optional revocation) | `${VITE_OPENEMR_BASE_URL}/oauth2/default/.well-known/openid-configuration` | `src/auth/oidcConfig.ts` reads it for logout + revocation. |

## Environment variables

| Var | Purpose |
|---|---|
| `VITE_OPENEMR_BASE_URL` | Root of the OpenEMR install. Used for OIDC discovery. |
| `VITE_OPENEMR_FHIR_BASE_URL` | FHIR root. Passed as `iss` to fhirclient. |
| `VITE_SMART_CLIENT_ID` | Public-client `client_id` from registration. |
| `VITE_DEFAULT_SCOPES` | Space-separated SMART scopes. **Use `Patient.rs`, not `Patient.r`.** |
| `VITE_USE_MSW` | `1` boots MSW for offline dev/test; `0` hits the real API. |

## Troubleshooting

- **CORS** — if the SPA cannot reach `/apis/default/fhir/*` from
  `http://localhost:5173`, uncomment the `server.proxy` block in
  `vite.config.ts` to proxy through the dev server. Pre-flight in §M of
  the Surprise plan's status companion verified CORS is permissive on
  this OpenEMR install, so the proxy should not be needed.
- **Self-signed cert** — visit `https://localhost:9300/` once in your
  browser and accept the cert. Playwright bypasses this with
  `ignoreHTTPSErrors: true` (configured in `playwright.config.ts`).
- **SMART app not enabled** — newly registered apps default to
  `is_enabled = 0`. Use the SQL UPDATE in "Register the SMART app"
  Option A or flip the toggle in the admin UI.
- **Wrong SMART discovery URL** — `fhirclient` discovers from
  `${iss}/.well-known/smart-configuration` where `iss` is the **FHIR
  base URL**, not the OAuth root. Setting `VITE_OPENEMR_FHIR_BASE_URL`
  correctly resolves this.
- **Logout fails** — the SPA discovers `end_session_endpoint` from the
  OIDC config. Never hard-code `/oauth2/default/logout`. (OpenEMR does
  not advertise a `revocation_endpoint`; the logout flow degrades
  gracefully when one is absent — clear sessionStorage, redirect to
  end_session.)

## Project layout

See `openemr/planning/Plan_wk2_Claude_Surprise01_2026-05-10_modern-patient-dashboard.md`
§4 for the full tree. High level:

```
src/
  auth/       SMART config, session, redact, OIDC discovery, logout
  fhir/
    client.ts wrapped getClient() + fhirGet<T>(path, schema)
    schemas/  Zod schemas (one per FHIR resource we read)
    queries/  named query functions (one per dashboard concern)
  models/
    dashboard.ts   FROZEN view-model contract — see CONTRACT.md
    adapters/      FHIR resource → view model (status filtering here)
  components/
    PatientHeader, DashboardGrid, cards/*, states/*, ui/*
  routes/    Launch, Callback, Dashboard
  styles/    tailwind.css
  test/      MSW handlers + server + browser worker + helpers + fixtures
tests/
  unit/      Vitest tests
  e2e/       Playwright dashboard smoke
  contracts/ Playwright mutation contract
```
