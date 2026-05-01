---
id: AgDR-0006
timestamp: 2026-04-30T23:55:00Z
agent: claude-code
model: claude-opus-4-7
trigger: user-prompt (continue plan_whole_opus47 build; integrate real Anthropic API; "use Haiku 3 to save money")
status: executed
---
# Use `messages.create()` with tool-use forced JSON, default to Haiku 4.5

> In the context of integrating the Clinical Co-Pilot sidecar with the live Anthropic API on a paid key,
> I decided to (a) replace the previously written `client.messages.parse(output_format=LLMOutput, cache_control={...})` call — which targets API surface that does not exist in the installed `anthropic==0.46.0` SDK — with `client.messages.create()` plus a single tool whose `input_schema = LLMOutput.model_json_schema()` and `tool_choice={"type":"tool","name":"emit_briefing"}`,
> and (b) default `COPILOT_MODEL` to `claude-haiku-4-5-20251001` rather than the user-requested `claude-3-haiku-20240307`,
> accepting Haiku 4.5's slightly higher per-token cost vs. Haiku 3 and dropping prompt caching for now (Haiku 3 was the cheapest option but is no longer addressable from the issued API key, and `claude-3-5-haiku-20241022` also returned 404),
> to achieve a working end-to-end loop today: fixture packets → real Claude call → Pydantic-parsed structured output → 8-rule verifier → green smoke test.

Alternatives considered:
- Stay on `messages.parse()` and bump to `anthropic>=0.92` — rejected: that version doesn't exist; the parse/structured-output API surface in the previous llm.py was hallucinated.
- Use freeform JSON in a text response and regex/`json.loads` — rejected: tool-use is the supported way to force a strict schema in current Anthropic models, and we already have the Pydantic schema.
- Switch the user to Sonnet 4.6 — rejected: user explicitly asked for the cheapest viable option to keep dev spend low; Haiku 4.5 is the cheapest model that actually responds for this key.

## Verification

- `python smoke_test.py` from `agent/copilot-api/` returns `verifier_status=passed` with 5 accepted claims against fixture packets, using `claude-haiku-4-5-20251001`.
- `python -m pytest tests/` is 18/18 green covering the verifier rules (source attribution, patient binding, active-status, trend, blank-vs-negative, refusal scope, drop+keep aggregation) and the schema boundary.
- `python -m evals.runner` remains 5/5; the verifier behavior is unchanged.
- The API key lives only in `agent/copilot-api/.env`; `git check-ignore -v` confirms it's gitignored at the repo root, plus a defensive sidecar-local `.gitignore`.
