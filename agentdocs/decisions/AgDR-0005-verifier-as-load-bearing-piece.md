---
id: AgDR-0005
timestamp: 2026-05-01T02:12:33Z
agent: claude-code
model: claude-opus-4-7
trigger: user-prompt (execute plan_whole_opus47_2026-04-30_build.md slice E)
status: executed
---
# Make the deterministic verifier the load-bearing trust component, not the LLM

> In the context of building a clinical co-pilot in a domain where wrong information has clinical consequences,
> I decided to gate every LLM-produced claim behind a small set of deterministic, source-attribution rules implemented in plain Python — not in a prompt — and to render to the physician only verified claims,
> accepting that some valid LLM output will be dropped and the brief will look thinner than it could,
> to achieve a strong, defensible answer to "how do you know what reaches the physician is grounded in the chart?".
> Alternatives considered: trust the LLM with `temperature=0` (rejected: no source attribution); use a "double-check" LLM call as the verifier (rejected: non-deterministic, can't be unit-tested with passing/failing fixtures); ship without a verifier and rely on prompt discipline (rejected: not defensible to a hospital CTO).

## Rules implemented

1. Schema valid (Pydantic parse).
2. Source attribution — every claim cites ≥1 source_id; every cited id must exist in the request packet set.
3. Patient binding — every cited packet's `patient_uuid` matches the request.
4. Active-status — claims using "current/active/on" require a packet with `status=active`.
5. Trend — `claim_type=trend` requires ≥2 source_ids.
6. Blank-vs-negative — absence claims require an explicit negative source value (NKDA, "no known", etc.), not absence of data.
7. Refusal-scope — claims that recommend / prescribe / diagnose / order are dropped.
8. Cross-patient — packets from another patient drop the claim.

A failed verification triggers one repair attempt with the verifier errors fed back to Claude. If still failing, unsupported claims are dropped and the brief renders only the verified subset with an explicit "couldn't verify X" line.

## Verification

- All 8 rules are exercised by `agent/copilot-api/evals/cases/*.json`; `python -m evals.runner` reports 5/5 pass.
- The verifier never raises — failures become structured `VerifierIssue` records on the response.
