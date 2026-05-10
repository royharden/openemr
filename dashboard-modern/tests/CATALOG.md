# Test Catalog

A running index of every test in this project, what it proves, and which
workstream owns it.

## Workstream 0 (orchestrator)

| File | Layer | Proves |
|---|---|---|
| `tests/unit/_smoke.test.ts` | Vitest | Every locked-signature query and adapter is exported as a function; `redact()` strips known token + PHI keys. |
| `tests/e2e/dashboard.spec.ts` | Playwright | SPA shell mounts at `/dashboard`. (W-D extends to all 6 cards.) |
| `tests/contracts/no-mutation.spec.ts` | Playwright | Read-only mutation contract skeleton. (W-D extends with token + revocation whitelist + plant-and-revert dry-run.) |

## Workstream A (SMART auth + FHIR client)

*To be filled in by Team A.*

## Workstream B (header + 3 cards)

*To be filled in by Team B. Must include adapter-side filter regression
test for at least Allergy and Condition.*

## Workstream C (3 more cards)

*To be filled in by Team C. Must include adapter-side filter regression
test for CareTeam status and the per-participant Practitioner-read path.*

## Workstream D (test harness + contracts)

*To be filled in by Team D. Owns the full mutation-contract impl with
plant-and-revert dry-run captured under
`dashboard-modern/agentdocs/regression-dryrun/`.*
