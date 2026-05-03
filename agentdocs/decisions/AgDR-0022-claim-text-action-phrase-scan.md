---
id: AgDR-0022
timestamp: 2026-05-03T05:01:00Z
agent: Codex
model: GPT-5
trigger: Direct HTTP sidecar probe after the immunization-packet fix showed the model placing "verify current status" inside claim text, a clinical-action phrase not covered by the previous caveat and missing_data sanitizers.
status: executed
---

# Apply prose-action phrases to claim text too

> In the context of the LLM moving clinical-action language between rendered
> prose fields, I decided to apply `PROSE_ACTION_PHRASES` to `claim.text` via
> the existing `refusal_scope` rule, accepting that a few otherwise factual
> claims will be dropped if they contain directive language, to ensure every
> rendered prose surface is covered by the same no-clinical-action contract.
> Alternatives considered: adding only `"verify current status"` to the prompt,
> leaving claim text covered only by the older `REFUSAL_TRIGGERS`, or adding a
> new separate verifier rule.

## Context

AgDR-0019 covered `missing_data`; AgDR-0020 covered `claim.caveat`. A live
sidecar call then returned a claim text sentence ending with "verify current
status." That phrase is not a medication order or diagnosis, but it still tells
the physician what to do, so it violates the product boundary of a read-only
briefing tool.

## Decision

- `PROSE_ACTION_PHRASES` now explicitly covers `claim.text`, `claim.caveat`,
  and `missing_data`.
- The verifier's first per-claim check now scans claim text against both
  `REFUSAL_TRIGGERS` and `PROSE_ACTION_PHRASES`; hits drop the claim under
  `refusal_scope`.
- Added `"verify current status"` to the shared phrase list and to prompt
  constraint #16 as a concrete forbidden example.
- Added a regression test where an allergy fact claim containing "verify
  current status" is dropped.

## Tradeoffs

This deliberately favors dropping borderline directive phrasing over letting it
render. Conflict-claim caveats retain the AgDR-0020 carve-out because the prompt
requires reconciliation caveats there; claim text has no such carve-out and
should stay descriptive.

## Verification

- `python -m pytest tests -q` passes 66/66.
- `python -m evals.runner` passes 22/22.
- Direct HTTP `/v1/brief` probe against restarted uvicorn with Maria's real
  packets failed the run if "verify current status", "Hepatitis", or "Hep A"
  appeared in the verified response; it exited 0.
