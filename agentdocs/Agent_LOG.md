# Agent Work Log

This file is the running chronological log of work performed by agents on this OpenEMR project. Future agents should append new entries at the top of the "Entries" section, leaving prior entries intact unless correcting a small factual typo.

Rules for future entries:
- Use UTC timestamps in ISO 8601 format.
- Identify the agent/tool and model when known.
- Summarize the user request, the repository context used, actions taken, verification performed, files changed, and any follow-ups.
- Keep sensitive values, private credentials, PHI, and unnecessary terminal noise out of the log.
- Record durable decisions separately in `agentdocs/decisions/AgDR-NNNN-description.md`.
- Record reusable surprises, pitfalls, and environment lessons in `agentdocs/agent_lessons.md`.
- Prefer links or paths to exact files over vague references.

## Entries

### 2026-05-02T02:55:00Z - Codex / GPT-5 - Planned free-text follow-up and final local completion work

Trigger: user asked whether the project is complete locally, called out the missing free-text chatbot, and requested a plan saved under `planning/` with prefix `plan_next01_codex_`, including remaining items from the Opus build plan/status.

Actions performed:
- Created `planning/plan_next01_codex_2026-05-02_free_text_and_final_local_completion.md`.
- Planned a constrained free-text follow-up surface that keeps the automatic pre-room brief and suggested buttons primary, while allowing current-patient, read-only, verifier-gated chart questions.
- Included implementation slices for UI, gateway router, sidecar schema/prompt, evals, local smoke, and documentation updates.
- Folded in remaining gaps from `plan_whole_opus47_2026-04-30_build_status.md`: Railway deploy, deployed smoke, demo video/README links, demo data, source chip behavior, sidecar task token validation, feedback persistence/docs, preventive-care wording, and gateway SQL wording.

Verification:
- Planning-only change; no tests run.

Files changed:
- `planning/plan_next01_codex_2026-05-02_free_text_and_final_local_completion.md`
- `agentdocs/Agent_LOG.md`

### 2026-05-02T02:11:00Z - Codex / GPT-5 - Post-commit documentation consistency cleanup

Trigger: user committed the previously dirty files and asked Codex to update anything left alone because of commit status, then make commits.

Actions performed:
- Updated active architecture deliverables (`ARCHITECTURE.md` and `planning/Architecture.md`) to reflect the implemented Langfuse Cloud US trace path instead of stale LangSmith references.
- Redacted the full Langfuse public key and direct project URL from `agentdocs/decisions/AgDR-0009-langfuse-cloud-us-activated.md`; retained the operational facts needed by future agents.

Verification:
- `rg` sweep confirmed the remaining `LangSmith` and `messages.parse` references are historical plan/log/AgDR context rather than current deliverable instructions.

Files changed:
- `ARCHITECTURE.md`
- `planning/Architecture.md`
- `agentdocs/decisions/AgDR-0009-langfuse-cloud-us-activated.md`
- `agentdocs/Agent_LOG.md`

### 2026-05-02T01:05:00Z - Codex / GPT-5 - Test, eval, and observability audit hardening

Trigger: user asked to audit the other agents' Clinical Co-Pilot work, specifically whether tests/evals/observability were appropriate and sufficient, and to make testing/evaluation changes while leaving broader architecture changes as report-only.

Context reviewed:
- `Week1-AgentForge.md` for PRD requirements around verification, observability, evals, deployment, cost analysis, and final deliverables.
- `planning/Architecture.md`, `planning/plan_whole_opus47_2026-04-30_build.md`, and `planning/plan_whole_opus47_2026-04-30_build_status.md`.
- `agent/copilot-api/app/{verifier,schemas,observability,orchestrator,llm}.py`, `agent/copilot-api/evals/`, `agent/copilot-api/tests/`, and the PHP gateway/audit files under `interface/modules/custom_modules/oe-module-clinical-copilot/`.

Actions performed:
- Hardened verifier patient binding to compare cited packet UUID hashes against the request's `patient_uuid_hash`, instead of trusting the first packet as the expected patient.
- Expanded the refusal-scope verifier triggers to catch treatment-adjustment wording such as dose increases/decreases and discontinuation, with a regression test.
- Added `agent/copilot-api/evals/cases/12_all_wrong_patient_packets.json` to catch an all-wrong-patient packet set.
- Updated `agent/copilot-api/evals/runner.py` to support optional per-case `request.patient_uuid_hash` and derive hashes for older fixtures.
- Added `agent/copilot-api/tests/test_observability.py` to check PHI-minimized Langfuse metadata, feedback score mapping, comment truncation, and configurable cost estimation.
- Added `estimated_cost_usd` to Langfuse trace/generation metadata and documented cost-rate env vars in `agent/copilot-api/.env.example`.
- Updated sidecar/eval/root README snippets and the execution status plan to reflect 29/29 pytest and 12/12 evals.
- Created `agentdocs/decisions/AgDR-0010-request-hash-patient-binding-eval-hardening.md`.

Verification:
- `cd agent/copilot-api; python -m pytest tests -q` - **29/29 passing**.
- `cd agent/copilot-api; python -m evals.runner` - **12/12 passing**, wrote `agent/copilot-api/eval_results.json`.

Files changed:
- `agent/copilot-api/app/verifier.py`
- `agent/copilot-api/app/observability.py`
- `agent/copilot-api/evals/runner.py`
- `agent/copilot-api/evals/README.md`
- `agent/copilot-api/evals/cases/12_all_wrong_patient_packets.json`
- `agent/copilot-api/tests/test_verifier.py`
- `agent/copilot-api/tests/test_observability.py`
- `agent/copilot-api/smoke_test.py`
- `agent/copilot-api/.env.example`
- `agent/copilot-api/README.md`
- `agent/copilot-api/eval_results.json`
- `README.md`
- `planning/plan_whole_opus47_2026-04-30_build_status.md`
- `agentdocs/decisions/AgDR-0010-request-hash-patient-binding-eval-hardening.md`
- `agentdocs/agent_lessons.md`
- `agentdocs/Agent_LOG.md`

Follow-ups / submission risks:
- Railway sidecar deployment and private networking smoke remain outstanding.
- Demo video and README deployed URL/Loom link remain outstanding.
- Production Langfuse trace and deployed OpenEMR `audit_master` join verification remain outstanding.
- Sidecar still accepts only the shared secret; the minted `X-Copilot-Task-Token` is sent but not validated by the sidecar. That is an architecture/security follow-up, not changed in this testing-only pass.

### 2026-05-01T23:00:00Z - Claude Code / claude-sonnet-4-6 - Langfuse Cloud credentials activated

Trigger: user provided Langfuse Hobby-tier API keys and asked to complete the integration.

Context reviewed:
- `agent/copilot-api/app/observability.py` — confirmed it reads `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
- `agent/copilot-api/.env` — no Langfuse vars present prior to this session.
- `agent/copilot-api/.env.example` — confirmed `LANGFUSE_HOST` is the correct var name for this project (SDK reads `host` kwarg from this env var).
- User's Langfuse project: "EMR-SO", org "REH", cloud region US (`us.cloud.langfuse.com`).

Actions:
- Added `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST=https://us.cloud.langfuse.com` to `agent/copilot-api/.env` (gitignored).
- Created `agentdocs/decisions/AgDR-0009-langfuse-cloud-us-activated.md`.
- Added lesson about `LANGFUSE_HOST` vs `LANGFUSE_BASE_URL` naming difference to `agentdocs/agent_lessons.md`.

Verification pending: start sidecar locally, POST a brief, confirm trace appears in Langfuse Cloud dashboard. Secret key stored only in `.env` (gitignored) — not logged here.

Files changed:
- `agent/copilot-api/.env` (added three Langfuse vars)
- `agentdocs/decisions/AgDR-0009-langfuse-cloud-us-activated.md` (created)
- `agentdocs/agent_lessons.md` (new entry)
- `agentdocs/Agent_LOG.md` (this entry)

### 2026-05-01T22:00:00Z - Claude Code / claude-opus-4-7 - Sunday Slices I–L (allergies/labs/immunizations builders, stale + sensitive + conflict verifier rules, 6 new eval cases, feedback loop, cost analysis)

Trigger: user asked to continue the build past the Thursday submission and finish the Sunday rubric — Slices I, J, K, L from `planning/plan_whole_opus47_2026-04-30_build.md`.

Context reviewed:
- `planning/plan_whole_opus47_2026-04-30_build_status.md` — outstanding Sunday slices and the noted "stale meds eval case" Thursday-parity gap.
- `agent/copilot-api/app/{schemas,verifier,orchestrator,main,observability,llm}.py` — to extend without re-architecting.
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/SourcePackets/{ActiveProblems,ActiveMedications,Identity}PacketBuilder.php` — to mirror the existing `freshness` + `PacketDto` shape.
- OpenEMR schema for `lists` (allergy rows), `procedure_order/report/result` (lab join), `immunizations` (CVX + administered_date) from `sql/database.sql`.

Actions performed:
- **Slice I:** New PHP builders `AllergiesPacketBuilder`, `RecentLabsPacketBuilder`, `ImmunizationsPacketBuilder`. Wired all three into `public/api/brief.php` with a `use_case` switch — `pre_room_brief` runs the full six builders; `medication_check`/`allergy_check`/`recent_abnormal_labs` run a focused subset. Allergies builder emits a synthetic NKDA packet when the chart records one explicitly so the verifier can distinguish "absence of data" from "explicit negative".
- **Slice J:** Three new verifier rules — `stale_data_uncaveat` (drops a claim if any cited packet is `freshness=stale` and the claim has no staleness caveat); `sensitive_data_uncaveat` (same shape, for `sensitive=true` packets); `lists_rx_conflict_unsurfaced` (post-processing — detects same-drug duplicates across `lists` and `prescriptions` and emits a `verifier_issues` + `missing_data` warning when the LLM didn't surface them as a `claim_type=conflict`). Added optional `sensitive: bool` to `SourcePacket` and three new `use_case` values to `BriefRequest`.
- **Slice K:** Six new eval cases under `agent/copilot-api/evals/cases/`: `06_stale_meds.json`, `07_lists_rx_conflict.json`, `08_sensitive_encounter.json`, `09_prompt_injection.json`, `10_latency_budget.json`, `11_allergy_conflict_surfaced.json`. Updated `evals/runner.py` to track per-case wall-clock time and check a new optional `verifier_max_ms` expectation.
- **Slice L:** New `public/api/feedback.php` gateway endpoint (CSRF + ACL-gated POST taking `{trace_id, verdict, comment}`); writes an OpenEMR audit row and forwards to the sidecar via a new `SidecarClient::callFeedback()` method. New sidecar route `POST /v1/feedback` posts a Langfuse `score` event keyed by the same `trace_id`. Panel UI gained five feedback chips and three new follow-up buttons (Medication check / Allergy check / Recent abnormal labs).
- **`planning/cost_analysis.md`:** Per-turn LLM math at ~$0.0073/turn (Haiku 4.5 with prompt caching, 5% repair rate). User/architecture/spend projections at 100 / 1K / 10K / 100K clinicians, including the architectural cliffs (Langfuse capacity, audit-row partitioning, Anthropic batch repair, self-hosted inference) that dominate before LLM cost does.
- **Prompt update:** `app/prompts/brief_v1.txt` extended to teach the LLM the new constraints (stale caveat, sensitive caveat, conflict surfacing, prompt-injection resistance) and document the four follow-up use-cases.

Verification:
- `python -m pytest tests/ -q` — **24/24 passing** (added 6 new tests for the three new rules).
- `python -m evals.runner` — **11/11 passing** (6 prior cases + 5 new + 1 Thursday parity).
- PHP `-l` syntax check on every new/edited PHP file inside the running OpenEMR container — no errors.

Files added:
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/SourcePackets/AllergiesPacketBuilder.php`
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/SourcePackets/RecentLabsPacketBuilder.php`
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/SourcePackets/ImmunizationsPacketBuilder.php`
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/api/feedback.php`
- `agent/copilot-api/evals/cases/{06_stale_meds,07_lists_rx_conflict,08_sensitive_encounter,09_prompt_injection,10_latency_budget,11_allergy_conflict_surfaced}.json`
- `planning/cost_analysis.md`
- `agentdocs/decisions/AgDR-0008-sunday-slices-i-through-l.md`

Files changed:
- `agent/copilot-api/app/schemas.py` (added `sensitive`, new use_case literals, `FeedbackRequest`/`FeedbackAck`)
- `agent/copilot-api/app/verifier.py` (rewrote — three new rules, per-claim and corpus-level)
- `agent/copilot-api/app/main.py` (added `POST /v1/feedback`)
- `agent/copilot-api/app/observability.py` (added `record_feedback` → Langfuse score)
- `agent/copilot-api/app/prompts/brief_v1.txt` (extended constraints + use-cases)
- `agent/copilot-api/evals/runner.py` (latency tracking)
- `agent/copilot-api/tests/test_verifier.py` (six new tests)
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/api/brief.php` (new builders + use_case switch)
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/Gateway/SidecarClient.php` (added `callFeedback`)
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/Controller/PanelController.php` (feedback chips + new follow-up buttons + feedbackUrl in JS config)
- `interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/js/copilot.js` (feedback POST wiring)

Follow-ups:
- Live sidecar exercise of `POST /v1/feedback` against Langfuse Cloud — needs the Railway deploy live with real Langfuse keys.
- Demo video must walk Sunday additions: panel renders allergies/labs/immunizations, feedback button posts, conflict surfacing visible, cost-analysis doc linked from README.
- Sensitive-flag detection in PHP builders is currently always `false`; v2 should derive `sensitive=true` from `lists.sensitivity`/`form_encounter.sensitivity` rather than passing it through inert.

### 2026-05-01T~18:00Z - Claude Code / claude-sonnet-4-6 - First professional git commit + push to GitHub and GitLab

Trigger: user asked to make a first real commit of all agent-built code, update `README.md`, understand the git/fork/PR workflow, and push to both GitHub and GitLab.

Context reviewed:
- `agentdocs/Agent_LOG.md` — prior agent work (Slices A–H, pytest suite)
- `git status` / `git log` — 2 existing unpushed commits (April 29 doc additions), plus unstaged moves and all new untracked work

Actions performed:
- Updated `README.md`: added a fork-description block at the top identifying this as a Gauntlet AgentForge fork, pointing to the key directories (module, sidecar, planning, agentdocs).
- Staged `git rm Architecture.md Audit.md Users.md` + `git add planning/` — git correctly detected these as renames (`R` status).
- Commit 1: `refactor(docs): relocate architecture and planning docs from root to planning/` (6 files, renames + new build plans).
- Commit 2: `feat(clinical-copilot): add AI clinical co-pilot module, FastAPI sidecar, and agent infrastructure` (65 files, 7932 insertions).
- Verified `agent/copilot-api/.env` was NOT staged (gitignored by `agent/copilot-api/.gitignore`).
- `git push origin master` → GitHub `github.com/royharden/openemr` — all 4 commits pushed.
- `git push gauntlet master` → GitLab `labs.gauntletai.com/royharden/openemr` — 2 new commits pushed (it already had the April 29 commits).

Verification:
- `git status` after commits: `nothing to commit, working tree clean`.
- `git log --oneline -4` shows all 4 custom commits above the upstream baseline.
- Both remote push commands returned success with correct SHA ranges.

Files changed:
- `README.md` (fork description block added)
- Commit history now reflects: add docs → revise docs → relocate docs → feat clinical-copilot

Notes:
- Remote `gauntlet` and `gitlab` both point to the same GitLab URL. Either works; redundant but harmless.
- No PR was created: since this is a solo fork with no upstream contribution intent, pushing directly to `master` is appropriate. For future feature work, create a branch first (`git checkout -b feature/name`), push that branch, then open a PR in the GitHub UI from that branch → master.

### 2026-04-30T23:55:00Z - Claude Code / claude-opus-4-7 - Wire real Anthropic API into sidecar; pytest verifier suite

Trigger: user asked to continue `planning/plan_whole_opus47_2026-04-30_build_status.md`. They saved an Anthropic key at `EMR-SO/Anthtropic-Dev-EMO-SH.txt` (outside the openemr git tree) and asked to use Haiku 3 to keep dev spend low.

Context reviewed:
- `planning/plan_whole_opus47_2026-04-30_build_status.md` — outstanding items: Railway deploy, demo video, deployed-URL §12 checklist, **pytest suite for verifier (Slice E)**, demo-DB augmentation.
- `agent/copilot-api/app/llm.py`, `app/orchestrator.py`, `app/schemas.py`, `app/verifier.py`, `evals/runner.py`.
- `anthropic` SDK installed: `0.46.0` (the previous llm.py targeted a non-existent API surface).

Actions performed:
- Rewrote `agent/copilot-api/app/llm.py`. Replaced the hallucinated `client.messages.parse(output_format=LLMOutput, cache_control=...)` with `client.messages.create(...)` plus a single tool whose `input_schema = LLMOutput.model_json_schema()` and `tool_choice={"type":"tool","name":"emit_briefing"}`. Pydantic validates the `tool_use` block input.
- Added `python-dotenv` loading at module import. Defensive double-load to handle a shell that exports `ANTHROPIC_API_KEY=` as empty (dotenv otherwise refuses to override).
- Added `agent/copilot-api/.env` (real key + `COPILOT_MODEL`), `agent/copilot-api/.env.example` (committed, no secret), and `agent/copilot-api/.gitignore` (defensive). Confirmed `git check-ignore -v agent/copilot-api/.env` resolves to `.gitignore:5:.env`. The key string appears in zero tracked files (`grep -r` clean).
- Tried `claude-3-haiku-20240307` (404 not_found), `claude-3-5-haiku-20241022` (404), `claude-haiku-4-5-20251001` (200). Locked the default to Haiku 4.5 — see `agentdocs/decisions/AgDR-0006-anthropic-sdk-tool-use-and-haiku-4-5.md`.
- Added a live end-to-end check at `agent/copilot-api/smoke_test.py`: 5 fixture packets (problems + meds for a fake patient) → real Claude call → verifier. Returns `verifier_status=passed` with 5 accepted claims.
- Built the pytest suite the plan called for: `tests/conftest.py`, `tests/test_verifier.py`, `tests/test_schemas.py`. Covers source attribution (empty + unknown id), patient binding, cross-patient citation, active-status (active vs discontinued), trend (≥2 sources), blank-vs-negative (NKDA vs blank), refusal scope (drops "I recommend insulin"), and the drop-unsupported-keep-supported aggregate path. Schema-boundary tests reject unknown `claim_type`, `answer_type`, and `use_case`. **18/18 passing.**

Verification:
- `python smoke_test.py` from `agent/copilot-api/` exits 0 with `verifier_status=passed`, 5 claims, 0 dropped.
- `python -m pytest tests/ -q` → `18 passed in 0.05s`.
- `python -m evals.runner` → `5/5 passed` (verifier behavior unchanged).

Files added / changed:
- `agent/copilot-api/app/llm.py` (rewritten)
- `agent/copilot-api/.env` (gitignored)
- `agent/copilot-api/.env.example`
- `agent/copilot-api/.gitignore`
- `agent/copilot-api/smoke_test.py`
- `agent/copilot-api/tests/__init__.py`
- `agent/copilot-api/tests/conftest.py`
- `agent/copilot-api/tests/test_verifier.py`
- `agent/copilot-api/tests/test_schemas.py`
- `agentdocs/decisions/AgDR-0006-anthropic-sdk-tool-use-and-haiku-4-5.md`
- `agentdocs/agent_lessons.md` (3 new entries)
- `agentdocs/Agent_LOG.md` (this entry)
- `planning/plan_whole_opus47_2026-04-30_build_status.md` (Slice E pytest box ticked + model note)

Follow-ups:
- Railway deploy of `copilot-api` service (Dockerfile ready) + `COPILOT_API_BASE_URL` wiring on the OpenEMR service.
- §12 smoke test against the deployed URL.
- Demo video.
- Optional: revisit prompt caching once we're on a model that supports it (Haiku 4.5 does — wire a `cache_control` block on the system prompt).

### 2026-05-01T02:12:33Z - Claude Code / claude-opus-4-7 - Clinical Co-Pilot module + sidecar build (Slices A–H)

Trigger: user asked to execute `planning/plan_whole_opus47_2026-04-30_build.md` end-to-end against the local Dockerized OpenEMR (`README-LOCAL-DOCKER.md`).

Context reviewed:
- `planning/plan_whole_opus47_2026-04-30_build.md` (build plan with 8 vertical slices)
- `agentdocs/OPENEMR_ARCHITECTURE.v2.md` (event names, ACL/CSRF surface, module bootstrap contract)
- `planning/Architecture.md` (Source Packet Contract, verifier rule set)
- `interface/modules/custom_modules/oe-module-dashboard-context/` as the canonical custom-module shape

Actions performed:
- Slice A: scaffolded `interface/modules/custom_modules/oe-module-clinical-copilot/` (composer, info, version, openemr.bootstrap.php, src/Bootstrap.php, src/Controller/PanelController.php, public/assets/{js,css}). Subscribes to `PatientDemographics\RenderEvent::EVENT_SECTION_LIST_RENDER_AFTER`. Registered the module by inserting into the `modules` table (`mod_active=1`, `type=0`).
- Slice B: built `public/api/brief.php` gateway. Verifies CSRF (subject `ClinicalCopilot`), checks ACL `patients/med`, reads `pid` and `encounter` server-side from `SessionWrapperFactory` (never from the request body), and generates a UUIDv4 `trace_id` per request.
- Slice C: built three packet builders — `IdentityPacketBuilder`, `ActiveProblemsPacketBuilder`, `ActiveMedicationsPacketBuilder` — backed by parameterized SQL on `patient_data` / `lists` (type='medical_problem' / 'medication') / `prescriptions`. PacketDto is a readonly value object including `freshness` enum.
- Slice D: built `agent/copilot-api/` FastAPI service. Pydantic schemas (single source of truth), `/healthz`, `/v1/brief` behind shared-secret auth. LLM call uses `messages.parse(output_format=LLMOutput)` with adaptive thinking and top-level `cache_control={"type":"ephemeral"}` on the stable system prompt.
- Slice E: built `app/verifier.py` with 8 rules in priority order (schema, attribution, patient-binding, active-status, trend, blank-vs-negative, refusal-scope, cross-patient). Repair-once is wired in `app/orchestrator.py`.
- Slice F: Langfuse instrumentation in `app/observability.py` — PHI-safe metadata only (hashed patient UUID, packet count, verifier status, token usage). OpenEMR-side `Audit/AgentTurnAuditor.php` writes one `EventAuditLogger` row per turn with the same `trace_id`.
- Slice G: 5 eval cases under `agent/copilot-api/evals/cases/*.json` plus `evals/runner.py`. `python -m evals.runner` reports 5/5 pass.
- Slice H: wrote per-component READMEs (`oe-module-clinical-copilot/README.md`, `agent/copilot-api/README.md`) with Railway deploy notes.

Verification:
- Logged in as `admin/pass`, opened demo patient (Phil Belford, pid=1) — module card rendered with `data-pid="1"` and the brief endpoint returned 7 source packets, `verifier_status=no_sidecar` (expected with sidecar absent).
- `python -m evals.runner` exits 0 with `5/5 passed`. Result artifact: `agent/copilot-api/eval_results.json`.
- Module visible inside the running OpenEMR container at `/var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/`.

Files added:
- `interface/modules/custom_modules/oe-module-clinical-copilot/` (entire tree)
- `agent/copilot-api/` (FastAPI service + Dockerfile + evals)
- `agentdocs/decisions/AgDR-0004-clinical-copilot-module-and-sidecar.md`
- `agentdocs/decisions/AgDR-0005-verifier-as-load-bearing-piece.md`

Follow-ups:
- Sidecar deploy on Railway — Dockerfile is ready; needs the `copilot-api` service spun up with `ANTHROPIC_API_KEY` and `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET`.
- Demo data does not include labs/vitals/allergies, so v1 builders are intentionally limited to identity / problems / meds. Sunday additions (`AllergiesPacketBuilder`, `RecentLabsPacketBuilder`, `ImmunizationsPacketBuilder`) per the plan.
- Demo patients (Phil Belford et al.) may need 1–2 pre-staged "recent abnormal" rows before recording the demo video; document any such augmentation in the README so it's not mistaken for real chart data.

### 2026-05-01T01:29:33Z - Codex / GPT-5 - Local Docker OpenEMR bring-up

Trigger: user asked to get the already-cloned OpenEMR app running locally with Docker Desktop so future code edits can be tested before GitHub commits.

Context reviewed:
- OpenEMR repository at `C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr`.
- Project planning and agent documentation locations, including `planning/`, `agentdocs/`, and the root project PRD.
- Official OpenEMR Docker documentation and the `docker/development-easy/docker-compose.yml` stack.

Actions performed:
- Confirmed Docker and Docker Compose were installed and callable.
- Chose the official OpenEMR `docker/development-easy` stack instead of creating a custom local compose file.
- Ran `docker compose up -d` from `openemr/docker/development-easy`.
- Waited through first-run bootstrap: image pulls, repository sync into the container, Composer install, Chromium/chromedriver install, npm install, theme compilation, quick OpenEMR setup, XDebug install, and Apache startup.
- Verified all development services came up: OpenEMR, MariaDB, phpMyAdmin, Selenium, CouchDB, OpenLDAP, and Mailpit.
- Verified OpenEMR login page loads at both `https://localhost:9300/` and `http://localhost:8300/`.
- Verified default credentials `admin` / `pass` by posting the login form and receiving a redirect to `/interface/main/tabs/main.php`.
- Attempted `/root/devtools register-oauth2-client`; it returned `client id: null` and `client secret: null`, so API client registration should be revisited when API work begins.

Verification:
- `docker compose ps` showed `development-easy-openemr-1` as healthy.
- Login page returned HTTP 200 after redirect from `/`.
- Authenticated form post with `admin` / `pass` returned HTTP 302 to the main tab screen.

Files changed by this entry:
- `agentdocs/Agent_LOG.md`
- `agentdocs/agent_lessons.md`
- `agentdocs/decisions/README.md`
- `agentdocs/decisions/AgDR-0001-use-official-easy-dev-docker.md`
- `agentdocs/decisions/AgDR-0002-wait-through-first-run-bootstrap.md`
- `agentdocs/decisions/AgDR-0003-verify-local-app-with-login-flow.md`
- `README-LOCAL-DOCKER.md`

Notes:
- No OpenEMR application code was changed.
- Git status already showed unrelated doc/planning moves before this documentation pass.
- The first Docker bootstrap was slow, especially on the Windows/OneDrive mounted tree; subsequent starts should reuse Docker volumes and be much faster.
