# Test Catalog

A running index of every test in this project, what it proves, and which
workstream owns it.

## Workstream 0 (orchestrator)

| File | Layer | Proves |
|---|---|---|
| `tests/unit/_smoke.test.ts` | Vitest | Every locked-signature query and adapter is exported as a function; `redact()` strips known token + PHI keys. |
| `tests/e2e/dashboard.spec.ts` (W0 skeleton) | Playwright | SPA shell mounts at `/dashboard`. (Extended by W-D below.) |
| `tests/contracts/no-mutation.spec.ts` (W0 skeleton) | Playwright | Read-only mutation contract skeleton. (Extended by W-D below.) |

## Workstream A (SMART auth + FHIR client)

*To be filled in by Team A.*

## Workstream B (header + 3 cards)

*To be filled in by Team B. Must include adapter-side filter regression
test for at least Allergy and Condition.*

## Workstream C (3 more cards)

*To be filled in by Team C. Must include adapter-side filter regression
test for CareTeam status and the per-participant Practitioner-read path.*

## Workstream D (test harness + contracts)

### Vitest — unit/component

| File | Layer | Proves |
|---|---|---|
| `src/test/helpers.tsx` | Test utility | `renderWithProviders` wraps a component with isolated MemoryRouter + QueryClient (retry off). `renderWithServer` also pushes MSW handler overrides. `createTestQueryClient` produces a bare QueryClient for focused tests. |
| `src/test/msw/server.ts` | Test utility | MSW node server instance; lifecycle (listen / resetHandlers / close) wired in `src/test/setup.ts`. `onUnhandledRequest: 'error'` ensures any unmocked fetch fails loudly. |

### Playwright — E2E smoke (mock mode, primary)

| File / test | Mode | Proves |
|---|---|---|
| `tests/e2e/dashboard.spec.ts` — "SPA shell mounts at /dashboard" | mock + live | React app bootstraps and routes correctly. |
| `tests/e2e/dashboard.spec.ts` — "all 6 section cards are visible" | mock | Allergies, Problem List, Medications, Prescriptions, Care Team, Lab Results headings all render (stubs or live). |
| `tests/e2e/dashboard.spec.ts` — "loading skeletons render" | mock | `aria-busy="true"` is present during loading state — accessibility and loading-state contract. |
| `tests/e2e/dashboard.spec.ts` — "no uncaught JS errors on mount" | mock | No `window.onerror` / `pageerror` events on initial render. |
| `tests/e2e/dashboard.spec.ts` — "SPA shell mounts at /dashboard (live mode)" | live only (`VITE_USE_MSW=0`) | Same boot assertion against real OpenEMR FHIR backend. |

### Playwright — Mutation contract (load-bearing gate, AgDR-0084)

| File / test | Proves |
|---|---|
| `tests/contracts/no-mutation.spec.ts` — "SPA never sends non-GET to /apis/default/" | Any `POST`/`PUT`/`PATCH`/`DELETE` against `/apis/default/` causes this test to fail. Whitelist: `/oauth2/default/token` (always) + `revocation_endpoint` if OIDC config advertises one (none on this OpenEMR per status §M). |
| `tests/contracts/no-mutation.spec.ts` — "whitelist covers the known token endpoint" | Sanity check that OIDC discovery returned at least one whitelisted URL and it includes the token endpoint. |

### Plant-and-revert regression evidence

| Location | Proves |
|---|---|
| `agentdocs/regression-dryrun/README.md` | Documents the plant-and-revert methodology. |
| `agentdocs/regression-dryrun/failing-output.txt` | Captured output of `npx playwright test tests/contracts/` when a deliberate `POST` was planted against `/apis/default/`. |
| `agentdocs/regression-dryrun/passing-output.txt` | Captured output after revert (test passes). |
