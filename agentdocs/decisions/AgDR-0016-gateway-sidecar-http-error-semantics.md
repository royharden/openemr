---
id: AgDR-0016
timestamp: 2026-05-02T19:10:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Slice C of plan_next02_opus47_2026-05-02_remediation_and_submission.md, in response to a codex audit finding that the gateway's `SidecarClient` decoded sidecar 4xx/5xx response bodies as if they were successful, causing `brief.php` to render auth failures as HTTP 200 successes with `verifier_status='unknown'`.
status: executed
---

# Gateway treats sidecar non-2xx responses as transport failures

> In the context of `SidecarClient::callBrief()` previously merging the
> sidecar's 4xx/5xx body with `__sidecar_status` and `brief.php` only
> branching on the absence of `__sidecar_error`,
> I decided to introduce a public `SidecarClient::classifyResponse(int,
> string)` seam that explicitly tags non-2xx responses with
> `__sidecar_error='http_error'` and propagates the status + detail,
> and split `brief.php`'s response shaping into three branches
> (verified, sidecar errored, no sidecar configured) instead of two,
> accepting that the sidecar-errored branch returns HTTP 502 with empty
> claims (no auto-fallback to packet-flattening),
> to achieve a denial matrix that can truthfully include "expired token",
> "tampered HMAC", and "patient_uuid_hash mismatch" rows — under the old
> behavior all three of those auth failures looked like a successful 200.

## Decision detail

- `SidecarClient::classifyResponse()` is `public static` so the new CLI
  smoke harness (`tests/sidecar_client_smoke.php`) can exercise it
  directly without spinning up Guzzle.
- Non-2xx → `{__sidecar_error: 'http_error', __sidecar_status, __sidecar_detail}`.
- Non-JSON 2xx body → `{__sidecar_error: 'invalid_json', __sidecar_status,
  __sidecar_raw}`.
- 2xx valid JSON → passthrough merged with `__sidecar_status`.
- `brief.php` branches:
  - **Sidecar configured + verified response (2xx + JSON)**: HTTP 200, full
    `VerifiedResponse` shape, audit row with the sidecar's
    `verifier_status`.
  - **Sidecar configured + errored**: HTTP **502**, empty `claims`,
    `missing_data: ['Verification temporarily unavailable for this turn —
    open the chart panels directly.']`, `verifier_status='sidecar_failed'`.
    Auto-fallback to packet-flattening is suppressed for this branch
    specifically — that was the change's whole point.
  - **No sidecar configured at all**: HTTP 200, packet-flattened pseudo-claims
    (preserved local-dev mode).
- `brief.php`'s top-level catch block now logs full exception detail
  server-side via `error_log(get_class($e) . message=...)` and returns only
  `{error: 'internal_error', trace_id}` to the browser. The previous
  behavior leaked `$e->getMessage()` (which can carry SQL fragments,
  internal paths, etc.).

## Tests

- New CLI smoke `tests/sidecar_client_smoke.php` — six cases:
  200 verified, 403 missing-token, 403 expired-token, 500 server, 502 empty
  body, 200 non-JSON body. Returns non-zero on regression. Run via
  `docker exec ... php tests/sidecar_client_smoke.php`.
- The router smoke (`tests/router_smoke.php`) is unchanged but should
  continue to be run alongside.
- The Python sidecar's auth tests already cover the missing/expired/
  tampered/mismatched-hash token paths (existing 41/41 → 50/50 after
  Slice B; the Slice C/D changes are PHP-only).

## Files changed

- `interface/modules/custom_modules/oe-module-clinical-copilot/src/Gateway/SidecarClient.php`
  — extracted `classifyResponse()`; both `callBrief` and `callFeedback`
  now route through it.
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/api/brief.php`
  — three-branch response shaping; exception leak redacted; HTTP 502 for
  sidecar errors; `error_log` retains full diagnostic detail server-side.
- `interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php`
  — new CLI smoke harness.

## Consequences

- The denial matrix in plan_next02_opus47 §J (Slice J — deployed smoke)
  can now be filled in honestly. Each forged-token variant produces a
  visible 502 + audit row, not a misleading 200.
- The Sidecar UX in the browser becomes "verification unavailable —
  open the chart panels directly," which is the right user-facing
  message when the AI side is down and the chart is still safe to use.
- The Langfuse view continues to show `verifier_status='sidecar_failed'`
  for these turns, which is filterable. Future agents adding sidecar
  features should keep the three-branch shape — collapsing it back to
  two is the regression that re-introduces the original bug.
