# plan_next04_codex_wise - Gateway Tool Planning, Evals, and Final Submission

**Target file:** `openemr/planning/plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`
**Status file:** Do not create a `_status` copy for this planning-only step.

## Implementation Status - 2026-05-03T07:47:34Z

This status copy was created because the implementation pass is now executing from the plan, and the project documentation notice asks implementing agents to preserve a `_status` handoff. The original plan file remains unchanged.

Completed locally:

- Added sidecar `POST /v1/tool-plan` with schema-validated tool calls and planner status.
- Added six read-only LLM-callable tool names: `get_patient_identity`, `get_active_problems`, `get_active_medications`, `get_allergy_list`, `get_recent_labs`, `get_immunization_history`.
- Added OpenEMR `ClinicalToolExecutor`; gateway executes selected tools only for the current session patient, rejects unknown tools and patient/SQL/table/source arguments, clamps lab `months`/`limit`, preserves packet cap 50, and falls back to a deterministic minimum map when no usable tools are returned.
- Kept local router refusals before tool planning for clinical-action and other-patient requests.
- Added `immunization_history` as a `BriefRequest.use_case`, PHP allowed use case, UI quick action, prompt constraint, schema test, and eval coverage.
- Added `selected_tools`, `planner_status`, and `tool_results_summary` to sidecar request/response, browser response, Langfuse metadata, and OpenEMR `agent_turn` audit comments without raw question text or clinical values.
- Expanded evals to 34 cases, including tool selection, patient-override args, unknown tool rejection, planner fallback, planner transport failure, and Pneumococcal-only immunization history.
- Updated `README.md`, `USER.md`, `planning/Users.md`, and `planning/Architecture.md` so the first reader sees the seven use cases, six tools, 34 evals, and gateway/verifier safety story.
- Added `tests/tool_executor_smoke.php`.

Verification completed:

- `python -m pytest tests -q` -> 71/71 passing.
- `python -m evals.runner` -> 34/34 passing.
- PHP lint clean on `brief.php`, `SidecarClient.php`, `ClinicalToolExecutor.php`, and `tool_executor_smoke.php`.
- `router_smoke.php` -> pass.
- `sidecar_client_smoke.php` -> 7/7 pass.
- `packet_builders_smoke.php` -> pass for demo pid 9001, Pneumococcal packet still correct.
- `agent_turn_auditor_smoke.php` -> pass.
- `tool_executor_smoke.php` -> pass.

Follow-up update - 2026-05-03T10:37:34Z:

- Retried PHPStan level 10 with Xdebug disabled and higher memory.
- The full OpenEMR `phpstan.neon.dist` still times out even on a single module file because it scans the large root project surface first.
- Added module-local `interface/modules/custom_modules/oe-module-clinical-copilot/phpstan.dist.neon` focused on the touched Co-Pilot files and required scan stubs.
- Fixed strict level-10 findings in `ClinicalToolExecutor.php`, `SidecarClient.php`, `PanelController.php`, `tests/tool_executor_smoke.php`, and `public/api/brief.php`.
- Verified with:
  - `php -d xdebug.mode=off -d memory_limit=2G vendor/bin/phpstan analyse -c interface/modules/custom_modules/oe-module-clinical-copilot/phpstan.dist.neon --memory-limit=2G --no-progress` -> no errors.
  - `python -m pytest tests -q` -> 71/71.
  - `python -m evals.runner` -> 34/34.
  - Docker PHP smokes for router, sidecar client, packet builders, tool executor, and agent-turn auditor -> pass.

Still remaining / not closed here:

- Internal-error browser probe, Langfuse cloud trace/cost review, full 7-workflow browser walkthrough, Railway deployment, deployed denial matrix, and demo video remain pending.

Follow-up update - 2026-05-03T10:57:49Z:

- Authored the human Railway update runbook at `../humanrunbooks/railway_update_app_codex_2026-05-03_bring_clinical_copilot_live.md`.
- The runbook translates the deployment slice into concrete human steps for the existing vanilla Railway project: add private `copilot-api`, set monorepo root `agent/copilot-api`, keep no public sidecar domain, set `PORT=8000` and `/healthz`, wire OpenEMR with `COPILOT_API_BASE_URL` and a shared secret, activate the custom module in the persistent database, seed/validate Maria G., then run browser/audit/Langfuse smoke.
- Actual Railway deployment, deployed smoke, deployed denial matrix, and demo video are still pending.

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
