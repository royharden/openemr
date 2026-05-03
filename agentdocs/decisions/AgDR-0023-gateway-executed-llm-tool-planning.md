---
id: AgDR-0023
timestamp: 2026-05-03T07:47:34Z
agent: Codex
model: GPT-5
trigger: Implement `plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`
status: executed
---

# Gateway-executed LLM tool planning

> In the context of the instructor feedback asking for LLM-callable clinical data tools with schemas, I decided to add a sidecar `/v1/tool-plan` step where the LLM chooses among six read-only tool names, while OpenEMR executes every selected tool inside the authenticated current-patient gateway. This accepts one extra LLM planning call on sidecar-backed turns to achieve a clearer agentic tool-planning story without giving the sidecar database credentials or patient-retargeting power. Alternatives considered: keep keyword-selected PHP bundles only, or let the sidecar call back into OpenEMR data endpoints directly. The first was weaker for the rubric; the second widened the trust boundary too much for Week 1.

## Verification

- `python -m pytest tests -q` -> 71/71.
- `python -m evals.runner` -> 34/34, including tool selection, forbidden args, unknown tool rejection, fallback, and tool transport failure cases.
- PHP smokes passed for router, sidecar-client response classification, packet builders, agent-turn audit logging, and the new `tool_executor_smoke.php`.
- PHPStan level 10 remains unresolved because the local container exhausted 512 MB and then timed out with `--memory-limit=1G`.
