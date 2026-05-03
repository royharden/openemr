# plan_next02_opus47 — Audit Remediation + Submission Path (STATUS)

**Status updated:** 2026-05-03T07:22:18Z by Codex / GPT-5.

### Update 2026-05-03T07:22:18Z - outstanding items rolled into Next04

The remaining local review probes, PHPStan level 10 completion, Railway deployment, deployed smoke/denial matrix, demo/README work, and submission housekeeping have been moved into `planning/plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`. Next04 also supersedes the final-submission path by adding the instructor-feedback recovery work: 7 first-class use cases, gateway-orchestrated LLM tool planning, and 34+ eval cases. These items remain **not done** until completed by the Next04 implementation.

## Implementation status summary

| Slice | Status | Notes |
|---|---|---|
| A. Demo seed schema fix (`procedure_report` chain) | **Done + live-verified** | Lab section rewritten to insert `procedure_order → procedure_report → procedure_result`. New `validate_demo_patient.sql` asserts the join shape. `demo/README.md` updated. **Live smoke caught three additional regressions in the original seed (not just the codex finding): missing `prescriptions.txDate`/`usage_category_title`/`request_intent_title` NOT NULL columns, unquoted reserved word `procedure_result.range`, and non-idempotent allergy/list-med inserts that leaked on re-run.** All fixed. Final validate counts match expected fingerprint exactly: 1/3/1/3/1/3/2/1. Idempotent across 3 sequential re-runs. |
| B. Verifier source-value grounding + prompt addendum + tests + evals | **Done** | New `source_value_mismatch` rule (numbers + ISO dates only — prose-overlap deferred to v2 per AgDR-0014). Prompt constraint #14 added. 9 new pytest cases; 4 new eval cases (19–22). 50/50 pytest, 22/22 eval. |
| C. Sidecar HTTP error semantics in `SidecarClient` + `brief.php` + smoke | **Done** | Extracted `SidecarClient::classifyResponse()` seam. `brief.php` now has three branches (verified / errored / no-sidecar). Errored branch returns 502 + `verifier_status='sidecar_failed'` and does NOT auto-fallback to packet-flattening. New `tests/sidecar_client_smoke.php` (6 cases). |
| D. `brief.php` exception redaction | **Done** (bundled with Slice C) | Top-level catch now logs full detail to `error_log` server-side; browser receives only `{error: 'internal_error', trace_id}`. |
| E. `llm.py` default model + `record_brief` router_family | **Done** | Default model pinned to `claude-haiku-4-5-20251001`. `record_brief()` accepts optional `router_family`; `process_brief()` passes `req.router_family`. New `tests/test_llm_default_model.py` source-pin guard. 2 new observability tests. |
| F. Root `USER.md` synchronization | **Done** | "Preventive gaps" → "Immunization history" everywhere; days-of-supply / fill-history examples replaced with v1-truth wording; USPSTF/ACIP claims removed (Use Case 5 retitled and explicit v2 deferral noted); feedback-loop language updated to two `trace_id`-keyed events (Langfuse score + `agent_turn` audit row); broken `Claude_Architecture_v2.md` link replaced with `Architecture.md`. `planning/Users.md` carries a canonicality note pointing at root. |
| G. Test + lint sweep | **Done + PHPStan moved to Next04** | `pytest tests -q` -> 53/53. `python -m evals.runner` -> 22/22. PHP smokes and `php -l` passed. PHPStan level 10 invocation is now tracked in the Next04 local verification gate, because new tool-planning PHP changes will also need PHPStan coverage. |
| H. Local Docker §12 smoke against fixed seed | **Moved to Next04** | Docker/browser smoke validated Maria G. rendered output, no Hep A, grounded lab values, follow-ups/free text, source-chip popover, sidecar-down HTTP 502 path, forged-pid terminal probe, and audit row query. Remaining review probes (internal-error browser probe, Langfuse trace/cost review, and PHPStan level 10 completion) are now tracked in Next04. |
| I. Railway sidecar deploy | **Moved to Next04** | Dockerfile is ready, but service is not provisioned. Railway private sidecar deployment is now tracked in Next04. |
| J. Deployed §12 smoke + denial matrix | **Moved to Next04** | Depends on Railway deployment. The deployed denial matrix is now tracked in Next04 and expanded for LLM tool-planning/tool-argument denial cases. |
| K. Demo video + README finalization | **Moved to Next04** | Final demo/README work is now tracked in Next04, including 7 use cases, LLM tool planning, source verification, Langfuse cost/tool metadata, and 34+ evals. |
| L. Submission housekeeping | **Moved to Next04** | Final commit/push/status housekeeping remains user-driven and is now part of the Next04 implementation/submission pass. |

## Verification commands (slices A–G plus later terminal/API smoke coverage)

```powershell
cd agent/copilot-api
python -m pytest tests -q          # 53/53
python -m evals.runner             # 22/22

# Docker/local terminal smokes:
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/router_smoke.php
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/agent_turn_auditor_smoke.php

docker compose -f docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr < agent/copilot-api/demo/seed_demo_patient.sql

docker compose -f docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr < agent/copilot-api/demo/validate_demo_patient.sql
```

Expected validation row counts: `patient_count=1`, `prescription_count=3`,
`list_med_count=1`, `lab_result_count=3`, `abnormal_lab_count=2`,
`immunization_count=1`. Anything else means the seed didn't run cleanly.

## Decisions recorded

- `agentdocs/decisions/AgDR-0014-source-value-grounding-verifier.md`
- `agentdocs/decisions/AgDR-0015-schema-correct-demo-lab-seed.md`
- `agentdocs/decisions/AgDR-0016-gateway-sidecar-http-error-semantics.md`

See the `agentdocs/Agent_LOG.md` 2026-05-02T19:10:00Z entry for the full
file-level changeset.

---

# Original plan (preserved verbatim below)

# plan_next02_opus47 — Audit Remediation + Submission Path

**Date:** 2026-05-02
**Author:** Opus 4.7 (planning, Claude Code)
**Repo:** `C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr`
**Inputs read & verified against live code:**
- `planning/plan_next02_codex_2026-05-02_audit_findings_remediation.md` (the codex audit being reviewed)
- `planning/plan_next01_opus47_..._review_and_final_local_completion{,_status}.md` (the previously executed plan + status)
- `planning/plan_whole_opus47_2026-04-30_build{,_status}.md` (original build + status)
- `Week1-AgentForge.md`, `planning/Architecture.md`, `planning/Users.md`, root `USER.md`
- Live: `agent/copilot-api/app/{verifier,llm,observability}.py`, `agent/copilot-api/demo/seed_demo_patient.sql`, `interface/modules/custom_modules/oe-module-clinical-copilot/{src/Gateway/SidecarClient.php,public/api/brief.php,src/SourcePackets/RecentLabsPacketBuilder.php}`
- Agent docs: `agentdocs/Agent_LOG.md` head entry, `AgDR-0001..0013`

This plan **does not edit** the codex plan. It (a) reviews the codex plan, (b) verifies its findings against live code, (c) folds them into the still-open submission slices from `plan_next01_opus47_..._status.md` (slices 8–12), and (d) gives a single ordered execution list a coding agent can run.

---

## 1. Verified status going in

From `plan_next01_opus47_..._status.md`, slices 1–7 are landed. I spot-checked the live files and they match the status report:
- Sidecar token validation, `patient_uuid_hash`, `tests/test_auth.py` — present.
- `QuestionRouter.php`, `LocalTraceLogger.php`, `/v1/trace/local_refusal`, `app/router_logic.py` — present.
- Free-text UI, source-chip popover, `packets_summary` — present.
- 41/41 pytest, 18/18 evals, PHP `router_smoke.php` — green per status.
- `demo/seed_demo_patient.sql`, `demo/README.md`, `AgDR-0011..0013` — present.

Slices 8-12 (local Docker §12 smoke, Railway deploy, deployed §12 + denial matrix, demo video, submission housekeeping) were pending in this plan after the lab-seed fix landed; their remaining unresolved work has now moved forward into `plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`.

## 2. Review of the codex plan

### What codex got right (keep verbatim)

1. **Finding 1 (verifier source-value mismatch).** Verified — `verifier.py` checks citation existence, patient binding, status, trend count, stale/sensitive caveats, refusal language, but never compares claim text values against cited packet values. A response saying `Lisinopril 100 mg` while citing a packet whose `value="Lisinopril 10 mg"` passes today. This is the single biggest remaining trust gap. Codex's lexical/numeric approach (extract numbers + dates from claim, require presence in cited packets' evidence concatenation) is the correct Week-1 shape — full clinical NLP would be over-engineering and would weaken the deterministic-verifier story.

2. **Finding 2 (lab seed schema).** Verified — `RecentLabsPacketBuilder.php:37-46` does `procedure_result pr INNER JOIN procedure_report prep ON prep.procedure_report_id = pr.procedure_report_id INNER JOIN procedure_order po ON po.procedure_order_id = prep.procedure_order_id`. The seed at `demo/seed_demo_patient.sql:82-101` writes `procedure_result.procedure_order_id` directly with no `procedure_report` row — the join finds zero rows, so Maria G. has zero lab packets. That kills "recent abnormal labs," the A1c trend story, and any free-text labs question in the demo. This is a P1 even though tests pass (the test suite uses fake packets, not the SQL).

3. **Finding 3 (sidecar HTTP error semantics).** Verified — `SidecarClient.php:73-84` decodes 4xx/5xx JSON body and returns it with `__sidecar_status` but no `__sidecar_error`. `brief.php:276` only branches on `__sidecar_error`. Result: a `403 {"detail":"task_token_missing"}` from the sidecar lands as a "successful" sidecar response; `verifier_status` becomes whatever the body says or `"unknown"`. The denial matrix in slice 10 cannot truthfully include "expired token" or "token hash mismatch" until this is fixed. Real P2.

4. **Finding 4 (`brief.php` leaks `$e->getMessage()`).** Verified — line 344 of `brief.php` puts the raw exception message in the JSON response. Internal stack info to the browser is a small but real leak. Easy fix.

5. **Finding 5 (root `USER.md` stale).** Verified — `USER.md:62`, `:66`, `:68`, `:131`, `:135`, `:136`, `:172`, `:174`, `:262`, `:280` reference "Preventive gaps," 90-day fill data, days-of-supply, USPSTF/ACIP-style preventive logic, and a dedicated feedback table — none of which is shipped. The PRD's submission table asks for `./USER.md`, so this is the canonical doc the grader sees first.

6. **Adjacent 7.1 (`llm.py` default model).** Verified — `agent/copilot-api/app/llm.py:22` still says `claude-3-haiku-20240307`. `.env.example` already says Haiku 4.5. If a deployer forgets to set `COPILOT_MODEL`, every deployed call 404s.

7. **Adjacent 7.2 (`record_brief` doesn't accept `router_family`).** Plausible from the file map; I'll let the implementing agent confirm. If true, free-text turns lose router-family filtering in Langfuse, which is a small observability hole.

8. **Adjacent 7.3 (source-chip deep links best-effort).** Codex is right not to expand this. Fix wording if a chip link 404s.

### Where the codex plan is thin or wrong-priority

These are the gaps I'd cover in addition to executing codex's recommendations:

1. **Codex stops at "remediation done" — but submission also needs slices 8–12 from the prior plan.** The PRD's deliverables table requires a deployed URL, demo video, README links, and a denial matrix. Codex's plan implicitly assumes someone else will run those. They have to be in this plan or they won't happen.

2. **Codex's order puts seed fix at #3.** Demo seed is the load-bearing demo asset — every smoke step (slice 8 onward) depends on it. Promote it to first or second; it's also a 5-minute SQL change vs. the verifier work that's a couple hours. Run it first, then the smoke step doesn't need to be re-run after the verifier work.

3. **Codex doesn't gate demo-video recording.** Without the demo seed fix, the Loom would either show "no labs" or use a different patient. The plan should explicitly say: *do not record the demo video before seed-fix smoke passes*.

4. **The "value-mismatch" verifier rule needs an explicit prompt addendum, not just a code rule.** Otherwise the LLM keeps emitting wrong-value claims and the verifier just drops more of them on every turn — that hurts the "verified by construction" defense and inflates `unsupported_dropped` in Langfuse. Add one paragraph to `prompts/brief_v1.txt` that explicitly says: *every number, dose, and date in your claim text must appear verbatim in at least one of the source packets you cite.*

5. **Codex's verifier rule over-asserts on prose.** The proposed condition rule ("require at least one meaningful non-stopword clinical token from the claim to appear in cited evidence") will false-positive on synonyms (`elevated`, `high`, `out of range` for lab abnormality language). Keep the rule strict on **numbers and dates** only for v1; leave free-prose token overlap to v2. This is an explicit narrowing of codex's rule, not a removal.

6. **Codex's eval renumbering is fine but should reuse `mode: "verifier_value_mismatch"`** rather than introducing a new mode. The existing eval runner already has `must_drop_some` semantics; the new cases just need to assert that `verifier_issues` contains `source_value_mismatch` for the offending claim_index.

7. **Codex doesn't say what to do if the sidecar return-shape change breaks the local-fallback rendering path.** `brief.php` currently has a "no sidecar configured" fallback that flattens packets into pseudo-claims. After the sidecar-error refactor, "sidecar HTTP error" should NOT fall through to that path — it should return `verifier_status="sidecar_failed"` with an empty claim list and the error visible. Codex says this in §4, but the implementing agent must remove the auto-fallback specifically for HTTP errors, not just the response shaping.

8. **PHPStan lint on the changed PHP files** is missing from codex's smoke list. The CLAUDE.md sets PHPStan level 10; introducing new ungated code without running `composer phpstan` is the kind of regression that bites at PR review time, even though the dev/test loop won't fail.

### Sufficiency verdict

Codex's plan is **excellent on the technical findings, ~70% complete on the path to a submitted Week-1 deliverable**. With (a) the order swap, (b) the prompt addendum, (c) the narrowed prose rule, and (d) explicit re-introduction of slices 8–12, it becomes the full submission plan.

## 3. My plan — single ordered slice list

Each slice ends in a runnable, demo-able state. Each slice that touches code must extend tests, observability, evals, and docs per `plan_next01_opus47` §3a (the cross-cutting rules). I won't restate them per slice — they apply.

### Slice A — Demo seed schema fix (codex Finding 2) *(do first; everything else depends on this)*

**Why first:** zero lab packets break every demo-flow smoke step. Five-minute SQL change.

Files:
- `agent/copilot-api/demo/seed_demo_patient.sql`
- `agent/copilot-api/demo/validate_demo_patient.sql` (new)
- `agent/copilot-api/demo/README.md` (update)

Tasks:
1. Rewrite the lab-result section to insert `procedure_order` → `procedure_report` → `procedure_result`, matching `RecentLabsPacketBuilder.php`'s join chain. One `procedure_report` row per order with `report_status='complete'`, `review_status='reviewed'`, `date_collected`, `date_report`. Three `procedure_result` rows referencing `procedure_report_id` (not `procedure_order_id`). Keep abnormal flags + values from the current seed (A1c 7.2 old, 8.4 recent abnormal, LDL 186 abnormal). Add `units` (`%`, `mg/dL`) and `range` so the lab builder produces stronger fact strings.
2. Make the section idempotent: delete in dependency order (`procedure_result` → `procedure_report` → `procedure_order`) keyed off `po.patient_id = @demo_pid AND po.order_diagnosis IN ('demo-a1c','demo-ldl')`.
3. Add `validate_demo_patient.sql` with three `SELECT` assertions: 1 patient, 3 lab results joined through `procedure_report`, expected abnormal+date counts. Anyone re-running the seed can eyeball the output.
4. Update `demo/README.md` with the new run order: seed, then validate, then expected counts.

Smoke (Docker required):
```powershell
docker compose -f docker/development-easy/docker-compose.yml exec -T mysql `
  mariadb -uroot -proot openemr < agent/copilot-api/demo/seed_demo_patient.sql

docker compose -f docker/development-easy/docker-compose.yml exec -T mysql `
  mariadb -uroot -proot openemr < agent/copilot-api/demo/validate_demo_patient.sql
```
Open Maria G. in the chart, click `Recent abnormal labs` — must show A1c 8.4 + LDL 186 with `source_table=procedure_result` chips.

Done when: validate query returns 3 lab rows; chart shows 2+ abnormal lab packets in the brief.

### Slice B — Verifier source-value grounding (codex Finding 1)

**Why second:** the highest-leverage trust improvement, and it's the slice with the largest test+eval surface, so doing it after the seed lets manual smoke catch any regressions on real lab data.

Files:
- `agent/copilot-api/app/verifier.py`
- `agent/copilot-api/app/prompts/brief_v1.txt` *(prompt addendum — codex didn't include this)*
- `agent/copilot-api/tests/test_verifier.py`
- `agent/copilot-api/evals/cases/19_value_mismatch_med_dose.json`
- `agent/copilot-api/evals/cases/20_value_mismatch_lab_result.json`
- `agent/copilot-api/evals/cases/21_value_mismatch_trend.json`
- `agent/copilot-api/evals/cases/22_value_mismatch_date.json`

Tasks:
1. **New verifier rule `source_value_mismatch`**, conservative-by-design:
   - Helper `_evidence_text(packet)` concatenates `label`, `value`, `unit`, `observed_at`, `last_updated`, `status`, `field`, lowercased + Unicode-normalized + dash/whitespace normalized.
   - Helper `_extract_numbers(text)` returns integer/decimal tokens, normalized (`10` and `10.0` are equivalent; `10` does **not** match `100`); skip numbers embedded in source IDs (`rx:prescriptions:101`).
   - Helper `_extract_dates(text)` returns ISO `YYYY-MM-DD` and US numeric dates from claim text.
   - Rule fires for `claim_type in {fact, trend, conflict}` only (skip `absence` since negative claims rarely contain values).
   - Every explicit number in the claim text must appear in at least one cited packet's evidence text.
   - Every explicit ISO date must appear in at least one cited packet's evidence text.
   - **Narrower than codex's rule on prose:** v1 does not require non-stopword clinical-token overlap. Codex's prose rule would false-positive on synonyms (`elevated` vs `high`, `abnormal` vs `out of range`). Numbers + dates only for v1; doc this as a v2 follow-up in the AgDR.
2. **Prompt addendum** (`brief_v1.txt`): add one paragraph to the existing CONSTRAINTS section: *"Every number, dose, frequency, and ISO date you write in claim text must appear verbatim in at least one of the source packets you cite. Do not paraphrase numerals. If a packet says `10 mg`, do not write `100 mg` or `ten mg`. The verifier will drop claims that violate this rule."* This reduces the rate at which the verifier has to drop claims, which keeps `unsupported_dropped` low and the "verified by construction" story clean.
3. **Tests** (extend `test_verifier.py`):
   - `test_source_value_mismatch_drops_wrong_med_dose` — packet `Lisinopril 10 mg`, claim `100 mg` → dropped.
   - `test_source_value_match_allows_correct_med_dose` — same packet, claim `10 mg` → passes.
   - `test_source_value_mismatch_drops_wrong_lab_value` — A1c packet `8.4`, claim `6.4` → dropped.
   - `test_source_value_mismatch_drops_wrong_observed_date` — packet `2026-04-20`, claim `2026-04-22` → dropped.
   - `test_trend_requires_values_from_both_sources` — packets `7.2` + `8.4`, claim `7.2 to 8.9` → dropped.
   - `test_source_id_numbers_are_ignored` — claim cites `rx:prescriptions:101` and says `10 mg` against a `10 mg` packet → passes (number `101` from source_id must not satisfy the `100` test).
4. **Evals**: 4 new cases (skip codex's optional `23_condition_wrong_source` per the narrowing in §6 above). Reuse existing `mode: "verifier_value_mismatch"`-like expectations: `must_drop_claim_at_index` + assert `verifier_issues` contains `source_value_mismatch`.

Done when: 47/47 pytest, 22/22 evals, the explicit `100 mg` vs `10 mg` probe is dropped with `source_value_mismatch`.

### Slice C — Sidecar HTTP error semantics (codex Finding 3)

Files:
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/Gateway/SidecarClient.php`
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/api/brief.php`
- `interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php` (new — CLI smoke, since this module has no PHPUnit harness)

Tasks:
1. In `SidecarClient::callBrief()` and `::callFeedback()`: after JSON-decode, if `$status < 200 || $status >= 300`, return:
   ```php
   ['__sidecar_error' => 'http_error',
    '__sidecar_status' => $status,
    '__sidecar_detail' => is_array($decoded) ? ($decoded['detail'] ?? null) : null]
   ```
   Do not merge the body in (today the body is overlaid — confusing).
2. In `brief.php`: split the existing branch:
   - If sidecar **not configured** (`$sidecarBase === ''`): keep current packet-flatten fallback for local-only dev.
   - If sidecar **configured** but `__sidecar_error` set: do **not** flatten packets into pseudo-claims. Return `verifier_status='sidecar_failed'`, `claims=[]`, `missing_data=['Sidecar verification unavailable for this turn — open the chart panels directly.']`, with HTTP 502 (gateway-perspective failure). Keep `trace_id`, `pid`, `patient_uuid_hash`, `packet_count`, `packets_summary` so the UI still has the audit pivot.
   - Always audit exactly one `agent_turn` row with `verifier_status='sidecar_failed'` for this case.
3. CLI smoke `tests/sidecar_client_smoke.php`: shape three mock decisions (200 valid, 403 missing-token, 500 server) into the new return type. Exit non-zero on regression. Wire it in alongside `router_smoke.php` in the `_status` smoke command list.
4. Sidecar Python: add 2 tests in a new `tests/test_main_routes.py` (or extend existing) using `fastapi.testclient.TestClient`:
   - missing `X-Copilot-Gateway-Secret` → 403.
   - valid secret + missing `X-Copilot-Task-Token` (with default `COPILOT_REQUIRE_TASK_TOKEN=1`) → 403 `task_token_missing`.

Done when: a deliberately bad token returns gateway 502 + audit row `sidecar_failed`; UI shows refusal-pill style error; PHP CLI smoke green; pytest still green.

### Slice D — `brief.php` exception redaction (codex Finding 4)

Files:
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/api/brief.php`

Tasks:
1. Remove the `'message' => $e->getMessage()` from the `catch` block JSON response. Keep `error_log(...)` server-side. Return only `['error' => 'internal_error', 'trace_id' => $traceId]`.
2. Audit-trail the trace_id in the `error_log` line so support can match a user's reported failure to a server log without exposing the message to the browser.

Done when: `rg "\$e->getMessage\(\)" interface/modules/custom_modules/oe-module-clinical-copilot/public/api` returns matches **only** inside `error_log(...)`, never inside response payloads.

### Slice E — Adjacent cleanup: model default + `record_brief` router_family (codex 7.1, 7.2)

Files:
- `agent/copilot-api/app/llm.py`
- `agent/copilot-api/app/observability.py` (`record_brief`, `record_local_refusal`)
- `agent/copilot-api/app/main.py` (`process_brief`)
- `agent/copilot-api/tests/test_llm_default_model.py` (new, tiny)
- `agent/copilot-api/tests/test_observability.py` (extend)

Tasks:
1. `llm.py:22` — change default to `claude-haiku-4-5-20251001`.
2. New test asserts `app.llm._MODEL == "claude-haiku-4-5-20251001"` when `COPILOT_MODEL` is unset.
3. `record_brief()` accepts `router_family: str | None = None` and emits it in trace metadata.
4. `process_brief()` passes `req.router_family` through.
5. `test_observability.py` — extend the existing free-text trace test to assert `router_family` lands in metadata.

Done when: 49/49 pytest passes; Langfuse free-text traces are filterable by `router_family`.

### Slice F — Root `USER.md` synchronization (codex Finding 5)

Files:
- `USER.md` (root)
- (optional) `planning/Users.md` — leave mirrored; do **not** delete since other planning docs link there.

Tasks:
1. Make root `USER.md` canonical. Copy the corrected v1-truth content from `planning/Users.md`.
2. Specific text fixes (line refs from current root `USER.md`):
   - L62, L83 (suggested-action buttons): `Preventive gaps` → `Immunization history`.
   - L66–L68, L131, L135, L136 (medication-adherence example): replace the days-of-supply/last-fill example with: *"Metformin appears on the active prescription list, but no fill or dispense record is present in the packets for this turn."* Acknowledge no fill data in v1 is the honest truth.
   - L167–L174 (Use Case 5): rename to "Immunization history". Add a short paragraph: *"v1 surfaces the immunization list with stale-data caveats. USPSTF/ACIP preventive-care guideline logic is v2 and is not shipped this week."*
   - L262 (feedback loop): replace "feedback table" with: *"Feedback events: a Langfuse score on the trace and an `agent_turn` audit row, both keyed by `trace_id`. v1 has no dedicated SQL feedback table — Langfuse + audit covers the rubric."*
   - L280: keep — it's still accurate.
3. Verify all relative links from root resolve. Fix any `./planning/Architecture.md` paths that should be `./planning/...` etc.
4. Optional but recommended: open `planning/Users.md` and add a one-line frontmatter note saying *"Mirror of root `USER.md`; root is canonical for the PRD submission."* Keeps internal links alive without contradicting the root.

Done when: root `USER.md` agrees with shipped behavior; no overclaims around fill history or preventive-care logic; the demo video script can read directly from it.

### Slice G — Test + lint sweep before re-running smoke

Tasks:
```powershell
cd agent/copilot-api
python -m pytest tests -q                # expect 49/49 (was 41/41; +8 from B+E)
python -m evals.runner                   # expect 22/22 (was 18/18; +4 from B)
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/router_smoke.php
docker exec development-easy-openemr-1 \
  php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php
docker exec development-easy-openemr-1 \
  composer phpstan -- --level=10 interface/modules/custom_modules/oe-module-clinical-copilot
```
Per `openemr/CLAUDE.md`, PHPStan must run on the full codebase but you can grep-filter output for changed files. If PHPStan flags anything in newly-touched files, fix at the source.

Done when: all four commands green; `php -l` clean on every changed PHP file.

### Slice H — Local Docker §12 smoke against fixed seed *(was slice 8 in plan_next01)*

This was the slice plan_next01 explicitly left pending. The terminal/API and most browser smoke work has since been exercised locally; the remaining review probes and final deploy proof are **Moved to Next04**.

Use the §12 list verbatim from `plan_next01_opus47_..._status.md`. Add three steps from this plan's findings:

11a. After clicking `Recent abnormal labs`: confirm the brief lists A1c **8.4** and LDL **186** with the *exact* numbers in the claim text — proves the new value-grounding rule isn't dropping legitimate matches.
11b. In DevTools, mutate the local sidecar URL env to point at a non-existent endpoint and re-run the brief. UI must render a refusal-styled "verification unavailable" message; audit row `verifier_status='sidecar_failed'`; HTTP 502 visible in the network panel.
11c. Trigger a known internal exception path (e.g., temporarily corrupt the gateway secret env to non-string) and confirm the response payload contains `error: internal_error` and `trace_id` only — no `message` field with stack content.

Document each result in `agentdocs/Agent_LOG.md` with screenshots/notes. If anything fails, return to A–G; do not proceed to deploy.

### Slice I — Railway sidecar deploy *(was slice 9 in plan_next01)*

Same env list as before. Two additional env vars from the codex plan:
- `COPILOT_REQUIRE_TASK_TOKEN=1` (already default; set explicitly so it's auditable in Railway).

Hard requirement: copy the new `validate_demo_patient.sql` to a Railway one-shot job so the deployed DB is verifiably seeded before the smoke step. If Railway DB cannot be seeded with synthetic demo data due to platform constraints, fall back to recording the demo against `localhost:8300` and noting in the README that "deployed instance uses a different demo patient; local Docker is the canonical demo seed."

### Slice J — Deployed §12 smoke + denial matrix *(was slice 10 in plan_next01)*

Plus the new auth-failure rows the codex plan called for:

| Attempted attack | Expected result |
|---|---|
| Forged `pid` in POST body | session pid wins; audit unchanged |
| Missing `csrf_token_form` | 403, `csrf_failure` audit |
| Logged-out `/brief.php` | 403/redirect, no audit |
| Sidecar called directly w/o `X-Copilot-Gateway-Secret` | 403 |
| **Sidecar w/ secret + missing token** | **403 `task_token_missing` (new)** |
| **Sidecar w/ secret + expired token** | **403 (new)** |
| **Sidecar w/ secret + tampered HMAC** | **403 (new)** |
| **Sidecar w/ secret + mismatched `patient_uuid_hash`** | **403 (new)** |
| **Gateway sees sidecar 4xx** | **HTTP 502 to browser, audit `sidecar_failed`, no leaked detail (new)** |
| **Gateway internal exception** | **HTTP 500 with `error=internal_error` + `trace_id` only, no message (new)** |

Each new row is the direct verification of a change in slices C, D, or A. Document each in Agent_LOG with a UTC timestamp.

### Slice K — Demo video + README finalization *(was slice 11)*

Same content as plan_next01 §11, with these changes derived from this plan:

- Demo script must explicitly demo a **value-grounding probe**: type "What dose of lisinopril is she on?" → see `10 mg, PO daily` with chip → say on camera *"and if I'd had the model write `100 mg`, the verifier would have dropped it — that's the source-value-grounding rule."* This sells the core trust feature directly.
- Demo script must show **one real source-chip popover** (not just a click) and call out the deep-link to the prescription record.
- Mention cost analysis on screen as plan_next01 said.
- Record the local-only backup video FIRST, before deploy, against the fixed seed. If Railway turns into a swamp the night of submission, you still have a video.

### Slice L — Submission housekeeping *(was slice 12)*

- Confirm root `AUDIT.md`, `USER.md`, `ARCHITECTURE.md` exist and link from root README.
- Conventional Commits + `Assisted-by: Claude Code` trailer per repo memory.
- Push to both `origin` (GitHub) and `gauntlet` (GitLab).
- Update both `_status` plans:
  - `plan_next01_opus47_..._status.md` — mark slices 8–12 done.
  - `plan_next02_opus47_..._status.md` (new — copy of this plan with checkboxes).
- New AgDRs (latest existing is `AgDR-0013`; pick next sequential):
  - `AgDR-0014-source-value-grounding-verifier.md`
  - `AgDR-0015-schema-correct-demo-lab-seed.md`
  - `AgDR-0016-gateway-sidecar-http-error-semantics.md`
- Append entries near the top of `agentdocs/Agent_LOG.md` and `agentdocs/agent_lessons.md`. Lessons worth saving:
  - "Verifier citations are not grounding unless values are also checked" — the simple, repeatable insight from this audit.
  - "OpenEMR labs require `procedure_order → procedure_report → procedure_result`. Skipping `procedure_report` produces zero rows from the standard join — the schema is non-obvious."
  - "PHP HTTP clients with `http_errors=false` will silently decode 4xx bodies as JSON — gateways must explicitly check status before treating the body as a successful response."

## 4. Recommended order in one line

`A → B → C → D → E → F → G → H → I → J → K → L`

Slices A–F can be a single PR (or two, splitting B from the others if reviewer attention is finite). G is a no-code lint sweep. H–L are environmental + submission. Do not skip ahead.

## 5. Submission readiness gate (the must-pass list before recording the final video)

All of these must be true:

- [ ] Lab seed runs cleanly; validation SQL shows 3 lab rows joined through `procedure_report`.
- [ ] Maria G. brief shows ≥2 abnormal lab packets with `source_table=procedure_result` chips.
- [ ] Verifier `100 mg` vs `10 mg` probe drops with `source_value_mismatch`.
- [ ] Verifier `2026-04-22` vs `2026-04-20` probe drops with `source_value_mismatch`.
- [ ] Gateway returns HTTP 502 + `verifier_status=sidecar_failed` + audit row when the sidecar replies 4xx, instead of HTTP 200 with confusing data.
- [ ] `brief.php` internal-exception response contains no `message` field.
- [ ] Root `USER.md` mentions only shipped features (Immunization history, free-text follow-up, no fill data, Langfuse+audit feedback).
- [ ] `llm.py` default model is `claude-haiku-4-5-20251001`.
- [ ] 49/49 pytest, 22/22 evals, both PHP CLI smokes green.
- [ ] PHPStan level 10 clean on every changed PHP file (**Moved to Next04** local verification gate, because Next04 introduces additional tool-planning PHP changes that need the same pass).
- [ ] Local browser smoke walked end-to-end against pid 9001.
- [ ] Local-only backup demo video recorded.

After that gate: deploy → deployed smoke → final demo video → README finalize → commit → dual push.

## 6. Risks specific to this plan

| Risk | Mitigation |
|---|---|
| Value-grounding rule is too strict and drops legitimate claims | v1 narrows the rule to numbers + ISO dates only (not free prose). New evals 19–22 cover the legitimate-pass cases too. Watch `unsupported_dropped` in Langfuse for the first 24h after deploy and tune. |
| Lab seed re-write breaks idempotency on dev DB that was already partly seeded | Delete in dependency order at the top of the section; explicit deletes of the demo `order_diagnosis` IDs prevent leftover rows from jamming the join. |
| Sidecar HTTP-error change breaks the existing local "no sidecar" fallback | Branch on `$sidecarBase === ''` *first*, separate from `__sidecar_error` — the local fallback only fires when no URL is configured at all, which is the dev-without-API-key case. Documented in the AgDR. |
| `USER.md` rewrite re-introduces stale claims | Use only `planning/Users.md` as the source; do not re-paraphrase from older drafts. The implementing agent should diff the result against this plan's §3 Slice F line list to confirm every required correction landed. |
| Railway DB cannot accept the synthetic demo SQL | Documented fallback: record demo against local Docker. The PRD allows this; the rubric does not require a specific deployed demo patient. |
| PHPStan flags issues in pre-existing files (not newly touched) | CLAUDE.md says fix at the source for any baseline entry on a touched file; otherwise leave existing baselines alone. Don't widen the baseline. |

## 7. What I'd still NOT do this week

The `plan_next01_opus47` §7 cuts list still applies verbatim. In addition, from this audit specifically:

- Codex's "condition fact requires clinical token overlap" rule (Finding 1, the prose-token bullet) — **deferred to v2**. Numbers + dates are enough for v1; prose-overlap is high-effort with high false-positive risk on synonym chemistry (high/elevated/abnormal).
- Codex's optional eval `23_condition_wrong_source.json` — **deferred** for the same reason.
- A dedicated PHPUnit harness for the gateway module — **deferred**. CLI smoke + PHPStan covers Week 1; full PHPUnit setup is a v2 task.
- Splitting `planning/Users.md` away from root `USER.md` — **deferred**. Mirroring is safer for Week 1; many planning docs link to `planning/Users.md`.

Each can be cited in the interview as "PRD does not require this" or "v2 work."

---

**Thesis line for the demo (unchanged):** *A clinical agent intentionally constrained — read-only, current-patient, source-cited, value-grounded, verifier-gated, observable, and deployed — because in a clinical context the trustworthy 30% beats the impressive 80%.*

The new word in the thesis is **value-grounded**, courtesy of codex's finding 1.
