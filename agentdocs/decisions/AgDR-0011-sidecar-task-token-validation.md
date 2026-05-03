---
id: AgDR-0011
timestamp: 2026-05-02T15:00:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Plan slice 1 from plan_next01_opus47_2026-05-02_review_and_final_local_completion.md — close the auth gap where the sidecar trusted only the shared secret and ignored the minted task token.
status: executed
---

# Sidecar task-token validation enforced

> In the context of preparing to deploy the Clinical Co-Pilot sidecar to Railway,
> I decided to validate the per-request HMAC task token at the sidecar (signature,
> expiry, scope, and patient-hash match) instead of trusting only the shared
> gateway secret,
> accepting the small risk that legacy callers without the token must opt out via
> `COPILOT_REQUIRE_TASK_TOKEN=0` (dev-only),
> to achieve per-request scoping so a leaked shared secret alone cannot exfiltrate
> data for arbitrary patients.
>
> Alternatives considered: (a) keep shared-secret-only and gate the sidecar
> behind Railway private networking — rejected because the secret is a single
> static credential with no per-request binding; (b) issue real JWTs with a JWKS —
> rejected as Week-1 overkill, no key rotation infrastructure exists yet.

## Decision detail

The gateway already minted `<base64-payload>.<hmac-hex>` task tokens via
`TaskToken::mint()` and sent them in the `X-Copilot-Task-Token` header, but the
sidecar's `auth.py` only inspected `X-Copilot-Gateway-Secret`. This decision
adds:

1. `verify_task_token()` in `agent/copilot-api/app/auth.py` — checks signature
   with `hmac.compare_digest`, decodes base64 payload tolerantly, and asserts
   `exp` (with 5s skew), `scope == "read-only"`, and the token's
   `patient_uuid_hash` matches `BriefRequest.patient_uuid_hash`.
2. `TaskToken.php` payload extended to carry `patient_uuid_hash` (truncated
   SHA256, the same hash the sidecar already received in the body) instead of
   the raw `patient_uuid` — keeps the token PHI-free in transit.
3. `/v1/brief` now requires the header by default; gated behind
   `COPILOT_REQUIRE_TASK_TOKEN` for dev backwards compatibility.
4. `tests/test_auth.py` covers valid / expired / tampered / wrong-scope /
   patient-mismatch / malformed / missing-secret / missing-exp paths.

## Verification

- `python -m pytest tests/test_auth.py -q` → 8 passing.
- `python -m pytest tests -q` → 41/41 passing (no existing tests regressed).
- Token payload renamed at the gateway from `patient_uuid` to
  `patient_uuid_hash` so the raw UUID never leaves the OpenEMR process.
