# Agent Lessons

This file captures reusable lessons, surprises, and environment-specific pitfalls discovered by agents. Future agents should append new lessons under "Entries" with a UTC timestamp, agent/model, short title, impact, and recommended handling.

Rules for future entries:
- Keep lessons practical and reusable.
- Include exact commands, paths, or symptoms when they help the next agent.
- Do not include PHI, private secrets, or noisy logs.
- If a lesson changes a durable project direction, also create an Agent Decision Record in `agentdocs/decisions/`.

## Entries

### 2026-05-03T10:57:49Z - Codex / GPT-5 - Updating a vanilla Railway OpenEMR deploy needs DB activation, not just pushed module files

Impact: The existing Railway deployment was initialized before the Clinical Co-Pilot module existed. Pushing the new module code to the `FLEX_REPOSITORY` branch gets files into the OpenEMR container, but the persistent MariaDB database still lacks an active `modules` row for `oe-module-clinical-copilot`. Without that row, `ModulesApplication::bootstrapCustomModules()` will not load `openemr.bootstrap.php`, so the chart card never renders.

Recommended handling: after redeploying OpenEMR from the branch with Co-Pilot files, explicitly activate the module in the deployed database and restart/redeploy OpenEMR. The human runbook `../humanrunbooks/railway_update_app_codex_2026-05-03_bring_clinical_copilot_live.md` includes an idempotent PHP/mysqli shell command for the Railway `openemr` service.

### 2026-05-03T10:57:49Z - Codex / GPT-5 - Railway sidecar deploy should pin the private port and keep the service domainless

Impact: The Co-Pilot sidecar Dockerfile listens on Uvicorn port 8000 and is intended for private OpenEMR-to-sidecar calls only. Leaving the port implicit or generating a public Railway domain makes troubleshooting and security posture worse: the OpenEMR variable should be `http://${{copilot-api.RAILWAY_PRIVATE_DOMAIN}}:8000`, and direct public calls should not exist.

Recommended handling: deploy `copilot-api` from monorepo root `agent/copilot-api`, set `PORT=8000`, configure healthcheck `/healthz`, keep one private replica, do not add a public domain, and set `COPILOT_REQUIRE_TASK_TOKEN=1`. Only the sidecar receives Anthropic/Langfuse keys; OpenEMR gets only `COPILOT_API_BASE_URL` and the matching shared secret.

### 2026-05-03T10:37:34Z - Codex / GPT-5 - For PHPStan on custom modules, use a focused module config and disable Xdebug

Impact: The root OpenEMR `phpstan.neon.dist` can time out or exhaust memory before analyzing targeted custom-module files because it scans the whole project surface. A focused module-local PHPStan config gives useful level-10 signal for touched module files in ~25 seconds.

Recommended handling: run:
```bash
docker exec development-easy-openemr-1 sh -lc "cd /var/www/localhost/htdocs/openemr && php -d xdebug.mode=off -d memory_limit=2G vendor/bin/phpstan analyse -c interface/modules/custom_modules/oe-module-clinical-copilot/phpstan.dist.neon --memory-limit=2G --no-progress"
```
Use the root config only when there is enough time and memory for whole-project analysis. Keep Xdebug disabled for analyzer runs.

### 2026-05-03T10:37:34Z - Codex / GPT-5 - Railway Hobby Plan is enough for the sprint if replicas and storage stay lean

Impact: The user's Railway Hobby Plan includes $5 monthly usage credit, up to 48 vCPU / 48 GB RAM per service, up to 5 replicas at 8 vCPU / 8 GB each, 5 GB storage, one developer workspace, community support, 7-day logs, and global regions. For this app, CPU/RAM are not the likely blocker; cost credits, storage, and keeping the sidecar private are the constraints to respect.

Recommended handling: deploy one public OpenEMR service, one private MariaDB service, and one private `copilot-api` sidecar at one replica each. Avoid Redis, extra workers, or extra replicas unless a smoke test proves they are needed. Keep logs short-lived and do not rely on Railway logs as durable audit storage.

### 2026-05-03T07:47:34Z - Codex / GPT-5 - Tool planning can be agentic without moving the trust boundary

Impact: The clean Week-1 compromise is not sidecar database access and not cosmetic tool labels. Let the LLM plan read-only tool names through `/v1/tool-plan`, then let PHP execute only allowlisted builders for the already-open OpenEMR patient. This satisfies the "agent chooses what data to pull" requirement while preserving patient binding, OpenEMR ACL/session/CSRF enforcement, no sidecar DB credentials, and verifier-gated rendering.

Recommended handling: keep local router refusals before tool planning; reject patient identifiers, SQL, table names, source IDs, and arbitrary query text in tool arguments; clamp benign numeric args in PHP; and add eval cases for unknown tools, patient-override args, empty planner fallback, and tool transport failure. See `AgDR-0023-gateway-executed-llm-tool-planning.md`.

### 2026-05-03T07:47:34Z - Codex / GPT-5 - OpenEMR PHPStan may need more than the default container memory

Impact: A targeted PHPStan level-10 run on the touched module files crashed at the default 512 MB PHP memory limit during PHPStan container generation. Re-running with `--memory-limit=1G` avoided the immediate crash but timed out after roughly 4 minutes in this local Docker/OneDrive setup.

Recommended handling: keep syntax checks and module smoke scripts as the fast local gate, and run PHPStan in a higher-memory/longer-time environment before final submission. Record the exact PHPStan failure instead of marking it green from a timed-out run.

### 2026-05-03T06:52:40Z - Opus 4.7 (Extended High thinking) - Pool-bounded tool-use is the cleanest "5 LLM tools with schemas" answer

Impact: The instructor explicitly asked for 5 LLM-callable tools with schemas AND for the agent to decide what data to pull. A pure tool-use refactor on every turn (Option A) breaks the speed budget for the pre-room brief and risks pushing data-access credentials into the sidecar (Audit S2 violation). A cosmetic relabel (Option B) doesn't satisfy the rubric. The defensible middle path is to pre-fetch the packet pool through the gateway as today (so the task token still bounds the data) and then expose 5 LLM tools whose implementations are pure pool filters inside the sidecar. The LLM picks tools; the pool stays bounded; the verifier still gates output; the sidecar still holds zero DB credentials.

Recommended handling: apply this only to the free-text path for v1 (named buttons keep the pre-fetch fan-out for the 90-second budget). Cap tool iterations at 3. Reject any `patient_uuid` tool argument server-side as defense-in-depth — the LLM must not be able to retarget the pool. Document the choice in `AgDR-0023-llm-tool-use-on-free-text-path.md`. Defense line: *"Pool bounded by the task token; LLM picks slices of the pool; verifier gates every claim."*

### 2026-05-03T06:11:00Z - Codex / GPT-5 - Codex-only browser smoke playbook lives in arcprep

Impact: The local OpenEMR browser smoke required Codex-specific browser-use patterns: in-app browser setup through the Node REPL, searching for `Maria`, clicking `G., Maria`, using DOM-CUA node IDs inside OpenEMR's framed UI, stopping/restarting uvicorn for sidecar-error probes, and pairing visual checks with terminal audit/packet smokes. Those details are reusable but specific to OpenAI Codex agents in the Codex desktop app.

Recommended handling: OpenAI Codex agents should read `arcprep/openai_codex_openemr_browser_smoke_playbook.md` before running the Maria G. local browser walkthrough. The playbook is explicitly for OpenAI Codex agents only; do not treat it as generic instructions for other agents or human testers.

### 2026-05-03T05:54:00Z - Codex / GPT-5 - Audit smoke has to read the actual log row, not just trust the auditor call

Impact: The browser UI looked healthy, but the audit query found no `agent_turn` rows. Server logs showed `AgentTurnAuditor` was calling `EventAuditLogger::instance()`, which does not exist in this OpenEMR version; the correct singleton is `EventAuditLogger::getInstance()`. Because the auditor catches exceptions, the user-facing request still worked and the failure only appeared in server logs.

Recommended handling: include `tests/agent_turn_auditor_smoke.php` in local smoke. It writes a synthetic `agent_turn` event and reads the decoded `log.comments` row back by trace id. When checking manually, query `log`, not `audit_master`, in this dev build:
```sql
SELECT id,date,event,user,success,FROM_BASE64(comments) AS decoded_comments,patient_id,category
FROM log
WHERE event='agent_turn'
ORDER BY id DESC
LIMIT 5;
```

### 2026-05-03T05:38:00Z - Codex / GPT-5 - Split smoke status into terminal/API proof vs logged-in browser proof

Impact: The earlier plan statuses said "Local Docker smoke pending," but later agents had already completed many of the deterministic pieces: seed validation, packet-builder smoke, router smoke, sidecar-client smoke, pytest/evals, and direct sidecar auth denial probes. Leaving those as plain pending made the project look less complete than it was, while marking the whole browser walkthrough done would have been equally misleading because rendered UI, DevTools, phpMyAdmin, and Langfuse checks still require a logged-in session.

Recommended handling: when reconciling overlapping plan statuses, mark broad smoke slices as "partially done" if terminal/API checks passed but the browser session was not walked. Keep deployed smoke separate from local smoke: Railway/deployed denial matrix items cannot be closed by localhost probes, even when the local probes exercise the same code paths.

### 2026-05-03T05:01:00Z - Codex / GPT-5 - If the model repeats a "hallucination," dump the source packets before tuning the verifier

Impact: The repeated "Hepatitis A" line looked like an LLM/verifier reload problem because the demo seed note said Pneumococcal and the verifier correctly dropped unsupported Hep A in isolated tests. Dumping the live source packets showed the packet itself said `"Hepatitis A 1"`. The model was following bad evidence, not inventing unsupported evidence. Root cause: `ImmunizationsPacketBuilder` joined OpenEMR's custom `list_options('immunizations')` table on `cvx_code`; in stock OpenEMR `list_options.option_id=33` is Hepatitis A 1, while real CVX code 33 resolves through `code_types`/`codes` to Pneumococcal PPSV23.

Recommended handling: before changing prompts/verifier rules for a repeated clinical entity, run the packet-builder smoke:
```powershell
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php --json
```
If packet evidence already contains the disputed entity, fix the packet builder or seed first. Verifier tuning is the wrong layer for bad source evidence.

### 2026-05-03T05:01:00Z - Codex / GPT-5 - OpenEMR immunizations have two naming systems: CVX `codes` and custom `list_options`

Impact: `immunizations.cvx_code` is a real clinical code and should resolve through `code_types.ct_key='CVX'` joined to `codes.code`. `list_options('immunizations')` is a legacy/custom display list keyed by `immunization_id`, not by `cvx_code`. Joining the custom list on `cvx_code` can silently produce a plausible but wrong vaccine name.

Recommended handling: mirror `interface/patient_file/summary/stats.php` for immunization display semantics. Prefer `codes.code_text` / `code_text_short` for `cvx_code`, fallback to `list_options` by `immunization_id`, then note/CVX fallback. Add seed validation for the meaning of clinically important codes, not just row counts.

### 2026-05-03T00:30:00Z - Claude Code / claude-opus-4-7 - "Rule works in pytest" ≠ "rule fires in live uvicorn"

Impact: The 2026-05-02 / 2026-05-03 smoke walkthroughs showed at least one case where the AgDR-0019 `missing_data_named_entity` rule should have dropped a "Hepatitis A" line but didn't, even though the new prompt's Pneumococcal worked example clearly made it into the running brief (so the prompt file had been reloaded). When I ran `verify()` end-to-end against the live brief content in isolation (synthetic packets matching the demo seed, missing_data containing the offending Hep A line), the rule fired correctly and dropped the entry. So the on-disk code is right and `pytest` proves the rule works — but somehow the live uvicorn process wasn't running it. The most likely cause is a partial module reload: FastAPI's `--reload` watcher may not always cleanly re-import every changed module, especially when files are edited while the process is alive. A "soft" reload can leave the old `_sanitize_missing_data` symbol resolved against an older closure even though the file on disk has the new one.

Recommended handling: when you change a verifier rule and need to confirm it's running live, do not trust `--reload`. Stop uvicorn entirely (`Ctrl-C` until the prompt returns), confirm the process is gone (`Get-Process uvicorn`), then restart. If a smoke result contradicts a passing pytest, the first hypothesis is "the running process is using stale code" — verify by adding a one-shot trace log line to the rule (e.g., `print(f"[sanitizer] dropping {entry!r}")`) and watching the uvicorn output during the next live request. If the trace line doesn't appear, the module wasn't reloaded.

This is also a reminder that integration tests against the running sidecar (the kind of LLM-in-the-loop harness AgDR-0019 explicitly defers to v2) would have caught this without needing a manual browser smoke. The cost-benefit math may shift in v2.

### 2026-05-02T23:30:00Z - Claude Code / claude-opus-4-7 - Prompt-only constraints are hints, not contracts — the verifier has to be the contract

Impact: I added prompt constraint #15 ("missing_data honesty — do not invent specific entity names") to `brief_v1.txt` and assumed it would stop the model from hallucinating "Hepatitis A" against a chart whose only immunization is Pneumococcal. After restarting uvicorn so the new prompt was loaded, the model still wrote "Immunization status beyond Hepatitis A (last dose 2019-10-12) — current status for influenza, tetanus, COVID-19 not documented." Same for "verify if still active" / "response plan" / "recommend review for cross-reactivity" — three turns, three different clinical-recommendation phrasings, all in `missing_data` prose, all bypassing the deterministic verifier because no rule gated that field.

The lesson: in a clinical agent, the trust story has to be deterministic. Prompts are how you give the model low-cost guidance; verifiers are how you make a promise to the user. Pure prompt control fails silently when the model wanders. The pragmatic v1 pattern is "constrain by prompt; backstop by verifier" — same thing we already do for claim text (constraint #14 + `source_value_mismatch` rule). Any field the brief renders that came from the LLM and is not subject to a verifier rule is a trust gap.

Recommended handling: every LLM-emitted field that survives into the rendered output (claims, caveats, missing_data, refusals, suggested_followups) needs at least one deterministic verifier rule. If a field's truth is inherently fuzzy (clinical interpretation, free prose), the verifier rule can be conservative (token-overlap, refusal-trigger scan, ISO-date grounding) — but it must exist. Skipping the verifier rule and relying on the prompt is a known anti-pattern; the model will eventually emit something the prompt didn't anticipate and there will be no defense.

### 2026-05-02T22:30:00Z - Claude Code / claude-opus-4-7 - OpenEMR chart panel placement is controlled by which RenderEvent constant you subscribe to, not by a numeric priority

Impact: I expected the OpenEMR PatientDemographics RenderEvent system to have a Symfony-style numeric `priority` argument I could raise to push our panel above other widgets. It doesn't — chart placement is controlled entirely by **which event constant you subscribe to**, and the dispatch sites for those constants are hardcoded into specific positions in `interface/patient_file/summary/demographics.php`.

The three choices (`src/Events/PatientDemographics/RenderEvent.php`):
- `EVENT_SECTION_LIST_RENDER_TOP` (line 1072 dispatch) — fires *before* `dashboard_header.php` and the patient nav menu. Too high for a chart card; the panel would render above the chart chrome itself.
- `EVENT_SECTION_LIST_RENDER_BEFORE` (line 1350 dispatch) — fires immediately before the `foreach ($sectionCards as $card)` loop. **This is the right slot for a card that should render above demographics / problems / meds / allergies / labs.**
- `EVENT_SECTION_LIST_RENDER_AFTER` (line 1529 dispatch) — fires after the section card loop. This is what the Co-Pilot module originally subscribed to — i.e. last on the page.

Recommended handling: when adding a chart-rail widget, read `interface/patient_file/summary/demographics.php` and find the three dispatch sites for these constants. Pick the one whose surrounding code matches your intended placement. Do not look for a numeric priority — there isn't one, and Symfony's `$priority` argument on `addListener()` has no effect across different event names.

### 2026-05-02T20:30:00Z - Claude Code / claude-opus-4-7 - "Schema-correct on paper" is not the same as "MariaDB will accept it"

Impact: Reading `sql/database.sql` to design a SQL fixture catches missing tables and wrong column names but misses three classes of bug that only surface when you actually execute against MariaDB:
1. **NOT NULL columns with no `DEFAULT` clause are silently fatal.** `prescriptions` has `txDate`, `usage_category_title`, `request_intent_title` with no defaults — any INSERT that omits them fails with `ERROR 1364`. Reading the column list, this is easy to skip because the eye expects "NOT NULL" to come paired with "default ''" elsewhere in the same table.
2. **Reserved words.** `procedure_result.range` is a real column but `range` is a MariaDB keyword, so an unquoted INSERT or SELECT errors out with a syntax error. `` `range` `` (backticked) works.
3. **Type coercion masquerades as success.** `prescriptions.unit` is `INT`, but `'mg'` doesn't error — MariaDB silently coerces to 0. The seed appeared to work for one column at a time but produced semantically wrong rows.

Recommended handling: every new SQL fixture must be exercised against a live MariaDB before committing. Pair it with a `validate_*.sql` that runs the same join shapes the production code uses, so discrepancies surface as count mismatches. When designing the fixture, grep the schema for `NOT NULL` rows that don't carry `DEFAULT` (`grep -E "NOT NULL,? *(COMMENT|--|$)"` against the table block) and add every one to the INSERT explicitly.

### 2026-05-02T20:30:00Z - Claude Code / claude-opus-4-7 - Idempotent SQL fixtures need explicit DELETEs on every section, not just "the dangerous ones"

Impact: My initial seed had DELETEs on the problems section and the labs section but not on the allergy or list-medication sections. After two re-runs, allergy and list-medication rows accumulated 3x. The verifier's `lists_rx_conflict_unsurfaced` rule then over-fires (or under-fires, depending on which copy the verifier indexes first), turning the demo non-deterministic.

Recommended handling: every INSERT in an idempotent fixture needs a same-pid + same-natural-key DELETE before it, period. The natural key is whatever distinguishes "this is the demo's row" from "this is something else" — usually `(pid, type, title)` or `(patient_id, drug)`. Don't trust "this section is small, it'll be fine" — small sections leak quietly and are noticed only when counts go off.

### 2026-05-02T19:10:00Z - Claude Code / claude-opus-4-7 - Citation existence is not value grounding

Impact: The deterministic verifier originally checked that every claim cited a real packet, that the packet belonged to the request patient, that "active" claims had an active packet, that trends had two sources, etc. — but it never compared the *values* in claim text to the values in cited packet evidence. A claim could say `Lisinopril 100 mg PO daily` while citing a packet whose `value` was `Lisinopril 10 mg PO daily` and pass every rule. That's the failure mode that defeats the "verified by construction" defense story without anyone noticing.

Recommended handling: any verifier that cites sources MUST also check that the numbers and dates in claim text appear verbatim in the cited evidence. v1 here narrows the rule to numbers + ISO dates only — free-prose synonym overlap (elevated/high/abnormal) has too much false-positive risk for a small win. Pair the runtime rule with a prompt addendum so the LLM stops emitting paraphrased numerals upstream rather than relying on the verifier to drop them. Keep number extraction word-boundary-strict and strip source IDs from claim text before extraction so digits inside IDs (`prescriptions:101`) don't masquerade as evidence.

### 2026-05-02T19:10:00Z - Claude Code / claude-opus-4-7 - OpenEMR labs require the `procedure_report` middle table

Impact: The intuitive shape for a lab fixture is `procedure_order → procedure_result`, and `procedure_result` does have a `procedure_order_id` *colloquially* — but it does NOT exist in the schema. The actual chain is `procedure_order → procedure_report → procedure_result`, and `procedure_result.procedure_report_id` is the FK. The Clinical Co-Pilot's `RecentLabsPacketBuilder` uses an INNER JOIN through all three, so a fixture that skips the report silently produces zero lab packets at runtime — even though the `INSERT` statements succeed and pytest passes (because tests use synthetic packets, not real SQL).

Recommended handling: any fixture or migration that touches labs must insert `procedure_report` rows. Use `LAST_INSERT_ID()` to chain `order → report → result` inserts. Pair every seed file with a `validate_*.sql` that runs the same join shape as the production code so a regression shows up as a count mismatch, not as a silently broken demo. Counts > 0 ≠ shape correct.

### 2026-05-02T19:10:00Z - Claude Code / claude-opus-4-7 - PHP HTTP clients with `http_errors=false` will silently decode 4xx bodies

Impact: Guzzle (and most HTTP clients) with `http_errors=false` returns a 200-shaped response object for any status code; calling `getBody()` and `json_decode()` on a 4xx body succeeds because most APIs return JSON `{"detail": "..."}` even on errors. If the gateway only branches on the absence of an `__sidecar_error` key, a 4xx auth failure looks like a successful response with `verifier_status='unknown'`. That hides real auth failures behind 200 OK and makes the denial matrix dishonest.

Recommended handling: always check `$status < 200 || $status >= 300` *before* treating the body as a successful response. Surface non-2xx as an explicit `__sidecar_error='http_error'` envelope (with status + detail) so downstream code has to pattern-match it, not silently merge it. Extract the status-classification logic into a public static method so a CLI smoke harness can exercise the seam without needing a live HTTP backend.

### 2026-05-02T15:45:00Z - Claude Code / claude-opus-4-7 - Eval runner needs a router-refusal mode for "no LLM call" cases

Impact: The eval runner exercises the verifier on a `(LLMOutput, packets)` pair. That shape can't express "the gateway should refuse this question without ever calling the LLM" — the strongest defense the agent has against treatment-recommendation requests. Without a runner-level mode for these, the eval suite silently misses the most security-relevant assertion (that the keyword router fired before any sidecar call).

Recommended handling: add `mode: "router_refusal"` to case JSON. The runner branches on this, calls a Python mirror of the PHP `QuestionRouter` (`app/router_logic.py`), and asserts `expected_family`, `expected_refusal_reason`, and `must_not_call_sidecar`. **Keep the PHP and Python routers in sync** — the PHP is authoritative; the Python is a test-only mirror. Both should change together.

### 2026-05-02T15:45:00Z - Claude Code / claude-opus-4-7 - HMAC tokens want the patient_uuid_hash, not the raw UUID

Impact: The first version of `TaskToken.php` carried `patient_uuid` (raw) inside the base64 payload, which means the raw UUID lived in HTTP headers en route to the sidecar — minor PHI exposure for no real benefit, since the sidecar already received `patient_uuid_hash` in the request body. The token only needs to *bind* the request to a patient, not *identify* the patient.

Recommended handling: tokens that travel in headers should carry the same hash the body already carries. Verifying token-hash == body-hash is enough to defeat replay across patients. Use `hmac.compare_digest` for both signature comparison and patient-hash comparison to avoid timing-side-channel surprises.

### 2026-05-02T15:45:00Z - Claude Code / claude-opus-4-7 - Eval cases that hard-code `request.patient_uuid_hash` will silently fail the patient-binding rule

Impact: Authoring a free-text eval case with a fabricated `patient_uuid_hash` (e.g. `"b2f9c1d3a456"`) plus packets whose `patient_uuid` doesn't hash to that value causes the verifier's `patient_binding` rule to drop every claim. The case appears to "fail" the verifier when really the case fixture is inconsistent.

Recommended handling: omit `request.patient_uuid_hash` from the case JSON unless you also set `patient_uuid` on every packet to a value that hashes to it. The runner's `_request_patient_hash` falls back to hashing the first packet's UUID, which is what most cases want. If you really do want a hash mismatch (to test cross-patient drops), set the override deliberately and call out the intent in the case description.

### 2026-05-02T01:05:00Z - Codex / GPT-5 - Patient-binding evals must include an all-wrong-packet case

Impact: The existing cross-patient eval covered a mixed packet set where the first packet belonged to the expected patient and the second did not. That let the verifier infer "expected patient" from `packets[0]`. It would still miss the more dangerous boundary where the whole packet set belongs to another patient but is internally consistent.

Recommended handling: include both mixed-patient and all-wrong-patient evals. The verifier should compare cited packet UUID hashes to the gateway-provided `patient_uuid_hash`, not to the first packet in the request. See `agent/copilot-api/evals/cases/12_all_wrong_patient_packets.json`.

### 2026-05-02T01:05:00Z - Codex / GPT-5 - Observability tests should assert what is *not* sent to the trace sink

Impact: A trace can look useful while accidentally storing PHI. The positive checks (trace_id, token counts, verifier status) are not enough; tests also need to assert absence of raw patient UUIDs, claim text, source values, or other high-risk payloads in metadata.

Recommended handling: keep trace metadata tests alongside the observability adapter. Use fake Langfuse clients to inspect emitted metadata without making network calls. Prefer hash, counts, timings, token usage, and estimated cost over raw clinical content.

### 2026-05-01T23:00:00Z - Claude Code / claude-sonnet-4-6 - LANGFUSE_HOST vs LANGFUSE_BASE_URL: Python SDK uses HOST, Cloud UI shows BASE_URL

Impact: The Langfuse Cloud dashboard `.env` snippet shows `LANGFUSE_BASE_URL` for the host. The Langfuse Python SDK v3 (and this project's `observability.py`) read `LANGFUSE_HOST`. Using `LANGFUSE_BASE_URL` means the sidecar ignores the env var and falls back to the default `https://cloud.langfuse.com` (EU), causing auth failures for accounts on the US region.

Recommended handling: always set `LANGFUSE_HOST` (not `LANGFUSE_BASE_URL`) in `.env`. The US region URL is `https://us.cloud.langfuse.com` — do not omit the `us.` subdomain prefix. If traces are not appearing in the dashboard, verify the host var first.

### 2026-05-01T22:00:00Z - Claude Code / claude-opus-4-7 - Conflict-surfacing rules are corpus-level, not per-claim — keep them out of the per-claim drop loop

Impact: The natural place to put a "duplicate medication appearing in both `lists` and `prescriptions`" check is inside `_check_claim`. That's wrong: the *absence* of a `claim_type=conflict` claim is what triggers the rule, so there's no per-claim hook to fire it on. Putting it in the loop either overfires (every fact claim citing one of the duplicates gets flagged) or never fires (no claim about either duplicate at all = silent). The right shape is post-processing over the *accepted* claim set, emitting a corpus-level warning into `missing_data` and `verifier_issues` rather than dropping anything.

Recommended handling: when a verifier rule depends on what the LLM *did not* say, write it as a separate function that runs after the per-claim loop (`_detect_lists_rx_conflicts` is the example). Keep the `_check_claim` loop strictly per-claim. Document the rule as "corpus-level" in the rule list so the next agent doesn't try to inline it.

### 2026-05-01T22:00:00Z - Claude Code / claude-opus-4-7 - Synthesizing an NKDA packet only when the chart already says NKDA preserves the blank-vs-negative invariant

Impact: It's tempting to have `AllergiesPacketBuilder` always emit a synthetic "NKDA" packet when the chart returns zero allergy rows, so the LLM has *something* to cite for "no known allergies". Don't. That defeats the entire blank-vs-negative rule — the verifier can no longer distinguish "we asked, the chart said NKDA" from "we asked, the chart returned nothing because nobody has filled in the allergies section yet". The first is safe to surface; the second is dangerous and must surface as `missing_data: "could not retrieve allergies"`.

Recommended handling: only emit an NKDA packet when there's a row in `lists` whose `title` regex-matches `\bnkda\b|no\s+known(\s+drug)?\s+allergies?\b`. Zero rows = empty packet list. The verifier's `blank_vs_negative` rule will then correctly drop any "no allergies" claim because there's no explicit-negative source to cite.

### 2026-05-01T22:00:00Z - Claude Code / claude-opus-4-7 - Optional fields on Pydantic schemas are backwards-compatible if you give them a default, even with the runner reading existing JSON cases

Impact: Adding `sensitive: bool = False` to `SourcePacket` means new eval cases can opt-in by setting it, and all five existing cases (which don't set it) still parse cleanly. The same trick works for the new `use_case` literal values — old `pre_room_brief` payloads still validate.

Recommended handling: when extending a Pydantic schema that's already serialized in JSON fixtures, always provide a default. Run `python -m evals.runner` immediately after the schema edit to catch any missing-default regression — the runner re-validates every JSON case through the Pydantic model.

### 2026-05-01T~18:00Z - Claude Code / claude-sonnet-4-6 - This repo has two remotes; always push to both after every commit

Impact: The project is published simultaneously to GitHub (`origin`, `https://github.com/royharden/openemr`) and Gauntlet GitLab (`gauntlet`, `https://labs.gauntletai.com/royharden/openemr`). Pushing to only one leaves the other stale, which matters because the Gauntlet evaluation environment reads from GitLab.

Recommended handling: After every `git commit` sequence, run both pushes:
```bash
git push origin master && git push gauntlet master
```
There is also a `gitlab` remote pointing to the same GitLab URL — this is a duplicate and can be ignored; `gauntlet` is canonical. See AgDR-0007 for the decision record.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - `messages.parse()` and top-level `cache_control=` don't exist in the Anthropic Python SDK

Impact: The previously written `app/llm.py` called `client.messages.parse(output_format=LLMOutput, cache_control={"type":"ephemeral"})`. Neither symbol exists in `anthropic==0.46.0` (and pyproject pinned an `anthropic>=0.92` version that doesn't exist on PyPI either). The whole sidecar was therefore non-functional against a real key — it would fail on the first call. The issue was masked because the only smoke path was the offline `evals.runner` (which imports the verifier directly and never hits the LLM).

Recommended handling: For structured output in current SDKs, use `client.messages.create(...)` with `tools=[{ "name": ..., "input_schema": MyModel.model_json_schema() }]` and `tool_choice={"type":"tool","name":...}`, then `MyModel.model_validate(block.input)` on the `tool_use` content block. `cache_control` belongs on individual content blocks (or not at all on older Haiku models), not as a top-level kwarg. Add at least one *live* smoke test (e.g. `smoke_test.py`) so the next agent doesn't ship a non-callable LLM path.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - Older Haiku model IDs return 404 from the issued API key

Impact: The user asked for "Haiku 3" to minimize cost. `claude-3-haiku-20240307` returned `not_found_error`. `claude-3-5-haiku-20241022` also returned `not_found_error`. `claude-haiku-4-5-20251001` worked. Likely cause: this account / API contract no longer routes to retired model IDs. Don't blindly accept "use the cheapest old model" — confirm the model is callable on *this* key before locking it in.

Recommended handling: When the user asks for a specific model that may be retired, run a one-line probe (`client.messages.create(model=ID, max_tokens=1, messages=[{"role":"user","content":"ping"}])`) and fall back upward (Haiku 3 → 3.5 → 4.5 → Sonnet) until you get a 200. Document the chosen model in `.env.example` so the substitution isn't silent.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - `dotenv.load_dotenv()` won't override an empty-string env var inherited from the shell

Impact: A parent shell that exports `ANTHROPIC_API_KEY=` (empty) defeats `load_dotenv()` because dotenv treats "already set" as "leave it alone" by default. Symptom: the `.env` is correct, `find_dotenv()` returns it, `load_dotenv()` returns `True`, and `os.getenv("ANTHROPIC_API_KEY")` is still `""`.

Recommended handling: After the first `load_dotenv()`, check whether the target keys are non-empty; if any are empty strings, call `load_dotenv(override=True)`. This is the pattern used in `agent/copilot-api/app/llm.py`.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - Custom modules require a row in the `modules` table

Impact: Dropping a module folder under `interface/modules/custom_modules/` is not enough — `ModulesApplication::bootstrapCustomModules()` only loads custom modules that have a row in the `modules` table with `mod_active = 1` and `type = 0` (custom, not Laminas). Without the row the bootstrap.php is silently skipped.

Recommended handling: Insert a row before testing module load, e.g.:
```sql
INSERT INTO modules
(mod_name, mod_directory, mod_parent, mod_type, mod_active, mod_ui_name,
 mod_relative_link, mod_ui_order, mod_ui_active, mod_description, mod_nick_name,
 mod_enc_menu, directory, date, sql_run, type, sql_version, acl_version)
VALUES
('Clinical Co-Pilot', 'oe-module-clinical-copilot', '', '', 1, 'Clinical Co-Pilot',
 '', 0, 1, 'Read-only AI co-pilot embedded in patient chart', 'copilot', 'no',
 'oe-module-clinical-copilot', NOW(), 1, 0, '0', '0');
```
Also: `dev-reset-install-demodata` truncates the modules table — re-insert after every reset.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - `CsrfUtils::verifyCsrfToken` signature is `(token, session, subject)`, not `(token, subject)`

Impact: `CsrfUtils::verifyCsrfToken($csrf, 'ClinicalCopilot')` looks like it should work but throws — the second positional argument is a `SessionInterface`, not the subject. Mirror `CsrfUtils::collectCsrfToken($session, 'ClinicalCopilot')` (subject is the trailing arg in both, but the session arg is mandatory in `verifyCsrfToken`).

Recommended handling: always pass the active session: `CsrfUtils::verifyCsrfToken($csrf, $session, 'ClinicalCopilot')`.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - mariadb client (not `mysql`) inside the Dockerized DB

Impact: `docker compose exec mysql mysql ...` returns `executable file not found in $PATH`. The image (`mariadb:11.8.6`) ships with `mariadb` but not the `mysql` symlink.

Recommended handling: use `docker compose exec mysql mariadb -uroot -proot openemr -e "..."`. Same flags, same SQL.

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - Brief gateway path traversal: 5 `../` from `public/api/brief.php` to globals

Impact: Custom-module ajax endpoints under `public/` need `require_once(__DIR__ . "/../../../../globals.php")` (4 `../`). One nested deeper at `public/api/brief.php` needs **5** `../`. Off-by-one breaks the include silently.

Recommended handling: count the path: `public/api/brief.php` → `public/` → `oe-module-.../` → `custom_modules/` → `modules/` → `interface/` → `globals.php` = 5 `../`.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - First Docker bootstrap is slow on Windows/OneDrive

Impact: The first `docker compose up -d` from `docker/development-easy` took a long time before OpenEMR served requests. The slow phases were repository sync, Composer install, Chromium/chromedriver installation, npm install, theme compilation, and ownership changes over the mounted tree.

Recommended handling: Do not assume the container is broken merely because OpenEMR is temporarily `unhealthy` during first bootstrap. Watch `docker compose logs --tail 200 openemr` and `docker compose exec -T openemr sh -lc "ps -o pid,etime,time,stat,comm,args | head"` to distinguish progress from a real stall. Avoid `docker compose down -v` unless intentionally resetting all warmed volumes.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - OpenEMR health JSON can be stricter than login readiness

Impact: `https://localhost:9300/meta/health/readyz` returned HTTP 200, but the JSON body included `status: setup_required` with `oauth_keys: false` even after Docker marked OpenEMR healthy and the login page worked.

Recommended handling: For local UI readiness, verify the login page and an `admin` / `pass` login flow. For API/OAuth work, revisit OAuth key/client generation separately before treating the API surface as ready.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - OAuth client helper did not produce usable credentials yet

Impact: Running `docker compose exec -T openemr /root/devtools register-oauth2-client` returned `client id: null` and `client secret: null`.

Recommended handling: Do not rely on Swagger/API OAuth testing until the OAuth keys/client registration path has been checked. The UI is runnable, but API validation needs a separate setup pass.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - Official easy-dev stack starts more than just OpenEMR

Impact: The local development stack also starts MariaDB, phpMyAdmin, Selenium, CouchDB, OpenLDAP, and Mailpit. This is heavier than a minimal app/database compose, but it matches OpenEMR's development tooling.

Recommended handling: Keep this as the default for brownfield development unless there is a clear reason to create a smaller task-specific compose file.
