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
