# Mutation Contract — Plant-and-Revert Dry Run

**Date:** 2026-05-10
**Owner:** Workstream D (team-d-tests-msw)
**AgDR:** AgDR-0084 (read-only mutation policy)

## Purpose

Prove that `tests/contracts/no-mutation.spec.ts` correctly detects any
non-GET request against `/apis/default/` before merging.

## Methodology

1. **Plant:** Created two temporary files:
   - `src/_dryrun_plant.ts` — exports a `deliberateMutation()` function
     that POSTs to `/apis/default/fhir/Patient`.
   - `tests/contracts/_dryrun_plant.spec.ts` — inverse assertion (proves
     the violation *is* detected).
   - `tests/contracts/_dryrun_fail.spec.ts` — production assertion applied
     to a page that executes the POST; this is expected to FAIL.

2. **Capture failing output:** Ran `npx playwright test
   tests/contracts/_dryrun_fail.spec.ts`. Exit code 1.
   Output saved in `failing-output.txt`.

3. **Revert:** Deleted all three plant files.

4. **Capture passing output:** Ran the production contract test
   `tests/contracts/no-mutation.spec.ts`. Exit code 0.
   Output saved in `passing-output.txt`.

## Key finding

The contract test correctly:
- **Fails** (exit 1) when `POST http://localhost:5173/apis/default/fhir/Patient`
  is present in the request stream.
- **Passes** (exit 0) with no mutations in the clean SPA (mock mode).

## Whitelist behavior

The OIDC discovery is attempted at test setup. Because this is mock mode
and MSW doesn't serve the OpenEMR OIDC config URL in the browser worker,
discovery falls back to the known value: `/oauth2/default/token`.

In live mode (VITE_USE_MSW=0), discovery hits real OpenEMR and reads the
actual `token_endpoint` plus `revocation_endpoint` if advertised. Per
status companion §M, `revocation_endpoint` is NOT advertised on this
OpenEMR, so the whitelist contains only the token endpoint.

## Files

| File | Purpose |
|---|---|
| `failing-output.txt` | Playwright output when POST is planted (exit 1) |
| `passing-output.txt` | Playwright output after revert (exit 0) |
| `README.md` | This file |
