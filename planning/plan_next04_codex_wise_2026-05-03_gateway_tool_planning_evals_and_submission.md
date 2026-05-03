# plan_next04_codex_wise - Gateway Tool Planning, Evals, and Final Submission

**Target file:** `openemr/planning/plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`
**Status file:** Do not create a `_status` copy for this planning-only step.

## Summary

After reviewing all seven `plan_next_04_*` drafts, the best path is to combine the strongest parts of the CodexExHigh/CodexHigh plans with the deadline discipline from the Opus/Sonnet plans.

Choose a **gateway-orchestrated LLM tool-planning flow**:

- The LLM really decides which clinical data tools to call.
- OpenEMR PHP still executes every selected tool inside the authenticated, current-patient gateway.
- The sidecar still has no database credentials.
- The verifier still gates every claim before the physician sees it.

This is stronger than the pool-filter shortcut because the instructor specifically asked for the agent to decide what data to pull, not merely filter data already pulled. It is safer than sidecar callbacks or sidecar DB access because the trust boundary stays in OpenEMR.

## Key Changes

- Add the requested plan file using the `plan_next04_codex_wise_` prefix only.
- Update `USER.md`, `README.md`, `Architecture.md`, and `planning/Users.md` so the first reader immediately sees:
  - 7 first-class use cases.
  - 6 LLM-callable read-only tools.
  - 34+ behavioral evals.
  - The verifier-gated, current-patient safety story.
- Add `immunization_history` as a first-class `BriefRequest.use_case`, PHP allowed use case, UI quick action, prompt use case, schema test, and eval case.
- Keep existing local refusals before tool planning: clinical-action and other-patient questions still refuse in the gateway with no LLM call.

## Tool-Calling Implementation

Add a sidecar endpoint:

`POST /v1/tool-plan`

Request fields:

- `trace_id`
- `use_case`
- `patient_uuid_hash`
- `question`
- `router_family`

Response fields:

- `trace_id`
- `planner_status`: `planned`, `fallback_required`, or `failed`
- `tool_calls`: selected tool names plus schema-valid arguments
- token/cost usage metadata

Expose these LLM-callable tools with JSON schemas:

| Tool | Gateway implementation |
|---|---|
| `get_patient_identity` | `IdentityPacketBuilder` |
| `get_active_problems` | `ActiveProblemsPacketBuilder` |
| `get_active_medications` | `ActiveMedicationsPacketBuilder` |
| `get_allergy_list` | `AllergiesPacketBuilder` |
| `get_recent_labs` | `RecentLabsPacketBuilder` |
| `get_immunization_history` | `ImmunizationsPacketBuilder` |

Tool rules:

- No tool schema accepts `pid`, `patient_uuid`, SQL, table names, source IDs, or arbitrary query text.
- Numeric arguments such as lab `months` and `limit` are clamped in PHP.
- Gateway executes only allowlisted tools.
- Packet cap remains 50 per turn.
- If `/v1/tool-plan` returns no usable tools, gateway uses the deterministic minimum map and records `planner_status=fallback_required`.
- If `/v1/tool-plan` fails at HTTP/network level, return the existing `sidecar_failed` 502 shape rather than pretending success.

Update gateway and sidecar contracts:

- Add `SidecarClient::callToolPlan()`.
- Add `ClinicalToolExecutor` in the module gateway layer to map tool names to builders.
- Add optional `selected_tools`, `planner_status`, and `tool_results_summary` to `BriefRequest` and the browser response.
- Include selected tools and planner status in Langfuse metadata and `agent_turn` audit comments, without raw question text or raw clinical values.

## Eval And Verification Plan

Expand evals from 22 to at least 34 cases.

Add cases covering:

- Tool selection for pre-room brief, medication, allergy, labs, identity, and immunization questions.
- Immunization history with Pneumococcal only and no invented Hep A, flu, COVID, or tetanus claims.
- Tool argument patient-override attempts.
- Unknown tool denial.
- Tool timeout or partial data behavior.
- What-changed with no supported delta.
- Missing-data category bounds.
- Stale medication caveat preservation.
- Allergy-medication conflict surfacing.
- Existing cross-patient and clinical-action refusals remain green.

Runner changes:

- Add `mode: "tool_plan"` for expected selected tools.
- Add `mode: "tool_error"` or equivalent mocked failure mode.
- Keep live LLM out of evals; mock tool-plan outputs for repeatability.

Required local verification:

```powershell
cd agent/copilot-api
python -m pytest tests -q
python -m evals.runner
```

```powershell
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/router_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/agent_turn_auditor_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/tool_executor_smoke.php
```

Also complete the prior-plan leftovers:

- PHPStan level 10 on touched module files.
- Internal-error browser probe confirms only `error=internal_error` and `trace_id`.
- Langfuse trace/cost review confirms tool-plan and synthesis spans with no raw PHI.
- Local browser walkthrough for all 7 workflows.

## Deployment And Submission

Deploy only after local tool planning and 34+ evals are green.

Railway requirements:

- `copilot-api` private network only, no public domain.
- `COPILOT_REQUIRE_TASK_TOKEN=1`.
- Fresh shared secret in OpenEMR and sidecar.
- No DB credentials in sidecar env.
- `display_errors` off for public OpenEMR.
- Default demo credentials rotated or clearly handled for demo-only use.

Deployed denial matrix must include:

- forged `pid`
- missing CSRF
- logged-out gateway request
- direct sidecar without gateway secret
- valid gateway secret with missing, expired, tampered, or mismatched task token
- unknown LLM tool
- patient identifier injected into tool args
- sidecar planner failure
- gateway internal exception redaction

Demo video must explicitly show:

- the 7 use cases in docs or README
- the Co-Pilot card in OpenEMR
- a tool-plan trace where the LLM chooses tools
- source-cited verified answer
- immunization history
- medication check
- abnormal labs
- free-text follow-up
- treatment refusal
- source-chip popover
- Langfuse cost/tool metadata
- eval runner showing 34+ passing cases

## Assumptions

- Current date is Sunday, May 3, 2026; do not use the incorrect May 4 Sunday date found in some draft plans.
- Existing dirty worktree changes are preserved and not reverted.
- `what-changed` remains the existing use-case string for now to avoid churn.
- No note RAG, write-back, prescribing, treatment recommendations, drug-drug interaction engine, or guideline engine in this plan.
- If time gets tight, do not downgrade to cosmetic tool docs. The minimum acceptable tool feature is real `/v1/tool-plan` plus gateway-executed selected packet builders.
