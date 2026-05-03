---
id: AgDR-0012
timestamp: 2026-05-02T15:30:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Plan slice 2 from plan_next01_opus47_2026-05-02_review_and_final_local_completion.md — add a constrained free-text follow-up while keeping the deterministic, source-cited verifier path intact.
status: executed
---

# Free-text follow-up via gateway-side keyword router

> In the context of the Week-1 PRD requiring an "agentic chatbot" but `Users.md`
> warning that a blank chatbot under a 90-second window is the failure mode,
> I decided to add a one-line free-text input that routes through a deterministic
> keyword classifier in the gateway and reuses the existing `VerifiedResponse`
> contract,
> accepting that the router will sometimes mis-classify novel phrasings (mitigated
> by a `fallback_chart_question` family that runs the full bundle),
> to achieve a constrained, testable, refusal-first chat surface where the LLM
> never picks which OpenEMR data to access.
>
> Alternatives considered: (a) LLM-based intent classifier — rejected because it
> doubles the surface for prompt injection without rubric credit; (b) a separate
> `/free_text` endpoint — rejected because two verification paths invite drift.

## Decision detail

- New PHP class `OpenEMR\Modules\ClinicalCopilot\Gateway\QuestionRouter` (pure
  function, no DB access). Returns `(family, builders, refusal_reason)`. Refuse
  families short-circuit before any packet is built or sidecar called. Order
  matters: `refuse_other_patient` precedes `refuse_clinical_action` precedes
  topical families precedes the catch-all.
- New schema fields on `BriefRequest`: `use_case=free_text_followup`,
  `question` (≤500 chars, control-chars rejected), `prior_turn_source_ids`
  (≤20 IDs, display-only context), `router_family` (observability metadata).
- Local-refusal trace path: gateway POSTs to a new
  `POST /v1/trace/local_refusal` endpoint so refused-by-router turns still get
  a Langfuse trace (estimated_cost_usd=0). One trace surface for all four turn
  outcomes: verified / repaired / refused-by-router / sidecar-failed.
- UI: one-line `<textarea rows=1>` with auto-grow, `Enter` submits,
  `Shift+Enter` newline. Maintains `window.OE_COPILOT_HISTORY` (last 3 turns)
  and forwards `prior_turn_source_ids` (IDs only, never prose).
- Eval coverage: cases 13-18, including a router-mode case that asserts
  `must_not_call_sidecar` for clinical-action and other-patient questions.
- Python mirror of the router lives in `app/router_logic.py` so the eval
  runner can exercise the same precedence offline. **Keep PHP and Python in
  sync.**

## Verification

- `python -m pytest tests -q` → 41/41 passing.
- `python -m evals.runner` → 18/18 passing.
- `php tests/router_smoke.php` (run inside the OpenEMR container) → all
  router cases pass, including a prompt-injection question that still routes
  to the labs family without exposing the injected directive to the LLM.
