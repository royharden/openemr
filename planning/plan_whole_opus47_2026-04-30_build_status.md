# plan_whole_opus47 — Clinical Co-Pilot Build Plan (execution status)

**Date:** 2026-04-30 (Thursday)
**Author:** Opus 4.7 (planning mode)
**Repo:** `C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr`
**Inputs digested:** [Week1-AgentForge.md](../../Week1-AgentForge.md), [Architecture.md](Architecture.md), [Audit.md](Audit.md), [Users.md](Users.md), [arcprep/architecture.md](../../arcprep/architecture.md), [OPENEMR_ARCHITECTURE.v2.md](../agentdocs/OPENEMR_ARCHITECTURE.v2.md), [openemr/CLAUDE.md](../CLAUDE.md), [Railway runbook v3](../../runbooks/opus47_deploy_openemr_railway_v3_mariadb.md).

---

## Status snapshot (Claude Code agent run — 2026-04-30 → 2026-05-01)

This file is a copy of `plan_whole_opus47_2026-04-30_build.md` with **_DONE** / **OUTSTANDING** / **DEFERRED** markers reflecting work performed by a Claude Code agent (Claude app), per its session summary and the current tree.

### Update 2026-05-01T22:00Z (Claude Code / claude-opus-4-7) — Sunday Slices I–L

- **Slice I** (allergies / labs / immunizations builders + follow-up routing) is **DONE**. Three new PHP packet builders shipped (`AllergiesPacketBuilder`, `RecentLabsPacketBuilder`, `ImmunizationsPacketBuilder`) and `public/api/brief.php` now switches builder sets on `use_case`.
- **Slice J** (verifier rules: stale-data labeling, sensitive-data caveat, lists/prescriptions conflict surfacing) is **DONE**. Three new rules in `app/verifier.py` + optional `sensitive: bool` on `SourcePacket`.
- **Slice K** (5 more eval cases) is **DONE**. Added `06_stale_meds.json` (Thursday parity), `07_lists_rx_conflict.json`, `08_sensitive_encounter.json`, `09_prompt_injection.json`, `10_latency_budget.json`, `11_allergy_conflict_surfaced.json`. **11/11 passing.**
- **Slice L** (feedback buttons → gateway → Langfuse score, plus AI cost analysis) is **DONE**. `public/api/feedback.php` (CSRF + ACL gated) + sidecar `POST /v1/feedback` writing a Langfuse `score` event keyed by trace_id; panel UI gained five feedback chips and three new follow-up buttons. `planning/cost_analysis.md` covers per-turn cost (~$0.0073) + 100/1K/10K/100K projections + architectural deltas.
- Full pytest run: **24/24 passing**. Eval suite: **11/11 passing**. PHP `-l` clean on every new file.
- See [AgDR-0008](../agentdocs/decisions/AgDR-0008-sunday-slices-i-through-l.md) for the decision record.

**Still OUTSTANDING after this session:** Railway deploy of sidecar service, demo video + README Loom URL, §12 smoke test on the *deployed* URL, Demo DB augmentation. Everything else on the Sunday rubric is checked.

### Update 2026-04-30T23:55Z (Claude Code / claude-opus-4-7)

- Sidecar LLM path is **live**. Rewrote `agent/copilot-api/app/llm.py` to use the real Anthropic SDK surface (`messages.create` + tool-use forced JSON) — the previous version called `client.messages.parse(...)` and a top-level `cache_control=` kwarg, neither of which exist in `anthropic==0.46.0`. End-to-end smoke (`python smoke_test.py`) now returns `verifier_status=passed` with 5 cited claims using `claude-haiku-4-5-20251001`.
- **Model selection:** user requested Haiku 3 for cost. `claude-3-haiku-20240307` and `claude-3-5-haiku-20241022` both 404 from this key. Locked `COPILOT_MODEL` to `claude-haiku-4-5-20251001`. See `agentdocs/decisions/AgDR-0006-anthropic-sdk-tool-use-and-haiku-4-5.md`.
- **Slice E pytest gap closed.** New `agent/copilot-api/tests/` covers the 8 verifier rules + schema boundary; **18/18 passing**.
- **Secret hygiene.** API key lives only in `agent/copilot-api/.env` (gitignored — `.gitignore:5:.env`). Added a defensive `agent/copilot-api/.gitignore` and a tracked `agent/copilot-api/.env.example`. Grep across the repo confirms zero tracked files contain the key string.


**Legend**

| Marker | Meaning |
|--------|---------|
| **DONE** | Implemented and exercised per agent report (local Docker), or artifacts exist in repo |
| **OUTSTANDING** | Still required for full alignment with this plan or Thursday smoke checklist |
| **DEFERRED** | Explicitly postponed to Sunday / v2 / operator action (unchanged from plan intent) |

**High-level**

| Area | Status |
|------|--------|
| OpenEMR module + chart panel | **DONE** (card + follow-up buttons + feedback chips + brief fetch) |
| Gateway `brief.php` (session pid, CSRF `ClinicalCopilot`, ACL, trace_id, use_case-switched builder set) | **DONE** |
| Six packet builders (identity, problems, meds, allergies, labs, immunizations) | **DONE** |
| Sidecar skeleton (`agent/copilot-api/`) FastAPI + LLM + verifier + `/v1/feedback` | **DONE** |
| Verifier (8 per-claim rules, repair-once, + Slice J stale/sensitive/conflict rules) | **DONE** |
| Observability + audit (Langfuse traces + `agent_turn` audit row + Langfuse `score` on feedback) | **DONE** at code level |
| Eval framework (`python -m evals.runner`) | **DONE** (11/11 passing) |
| Sidecar Dockerfile + README / env docs | **DONE** |
| Pytest suite (`tests/test_verifier.py` etc.) | **DONE** — 24/24 passing in `agent/copilot-api/tests/` |
| Sunday slices I–L (extra packet builders + verifier rules + 5 evals + feedback + cost analysis) | **DONE** (see 2026-05-01T22:00Z entry) |
| Railway deploy + private networking + OpenEMR env wiring | **OUTSTANDING** (Dockerfile ready; service not deployed) |
| Demo video + README Loom URL | **OUTSTANDING** |
| §12 full checklist on **deployed** Railway URL | **OUTSTANDING** (verified locally: admin, patient chart, brief endpoint) |
| Demo DB augmentation (thin labs) | **OUTSTANDING** / optional before video |
| Agent docs (Agent_LOG, lessons, AgDR-0004/0005/0006/0008) | **DONE** |

**Eval cases vs plan wording:** Thursday parity gap closed. Added `06_stale_meds.json` covering the explicit stale-meds / freshness-labeling scenario from §7 Slice G. Eval suite is now 11 cases total (Thursday 5 + Sunday 5 + 1 parity).

---

## 1. Context

OpenEMR is forked, deployed on Railway with demo data via the `flex` image, and the Tuesday MVP submission (audit, users, architecture, deployed URL) is in. The remaining work is to put **a real, demonstrable Clinical Co-Pilot** behind the deployment that meets the AgentForge agent requirements: agentic chatbot, verification system, observability, and an eval framework.

The user already locked in the *what* (read-only, current-patient, source-cited, sidecar-orchestrated, Railway-deployed). This plan is the *how*: a time-boxed execution plan keyed to two deadlines and a brownfield codebase whose extension points are now confirmed by a code-level audit (see §6).

## 2. The deadline reality (read this first)

| Checkpoint | Deadline | Status |
|---|---|---|
| Tuesday MVP | 2026-04-28 23:59 CT | ✅ Submitted |
| **Early Submission** | **2026-04-30 23:59 CT (TODAY)** | 🔴 ~10–12 hours from now |
| Final | 2026-05-03 12:00 CT (Sunday noon) | 🟡 ~3 days |

**Implication:** Thursday is not "ship the full agent." Thursday is "ship the smallest credible agent slice that is end-to-end demonstrable on the deployed URL with traces and one eval case." Sunday is "the version a hospital CTO defends." Plan accordingly. **Don't burn Thursday hours building Sunday-grade pieces.**

If the early-submission window is already too tight to deploy, then ship a **local** demo for Thursday with a clear note, and use the Friday–Sunday window to deploy the agent service to Railway. Submission rubric requires a deployed agent at *Final*, not Early.

## 3. Decisions locked in (won't relitigate)

These come from existing planning docs and stay locked:

1. Read-only v1; no diagnose / prescribe / order / write-back.
2. Current-open-patient binding only; cross-patient requests rejected at gateway.
3. Sidecar holds **zero** MariaDB credentials.
4. All clinical data flows through OpenEMR — preferred order: services in `src/Services/` → standard REST → FHIR. Direct SQL forbidden in agent code.
5. LLM is the language layer, not the source of facts. Source packets + deterministic verifier gate every claim.
6. Patient `pid` and `encounter` come from the **server session**, never from request bodies or model outputs.
7. Structured data only in v1. No note RAG, no vector DB, no DDI engine.
8. Anthropic Claude (Sonnet 4.6 default; Haiku 4.5 for cheap repair calls) under assumed BAA per Gauntlet rules.
9. Langfuse for traces (Cloud for class, self-hostable path documented for prod).
10. Deploy target: Railway, add **one** new private service (`copilot-api`). Optional Redis only if time allows.

## 4. Architecture in one paragraph

Browser ↔ OpenEMR (auth + chart panel) ↔ **Co-Pilot Gateway** (PHP, inside the OpenEMR custom module — does session/CSRF/ACL/patient-binding, builds source packets via OpenEMR services, mints a 15-minute task token, and forwards to the sidecar over Railway private networking) ↔ **`copilot-api`** (Python FastAPI — orchestrates the LLM, validates structured output, runs the deterministic verifier, emits Langfuse spans, returns verified claims) ↔ back to gateway, which writes the `agent_turn` audit row and renders. The full picture is already drawn in [Architecture.md](Architecture.md#system-architecture); this plan does not re-draw it.

## 5. Scope by deadline

### Thursday (Early Submission) — minimum credible slice

| Required by AgentForge | Thursday version |
|---|---|
| Agentic chatbot | Pre-room briefing + 1 follow-up button (`What changed?`) + free-text (current patient only). Tool-using, multi-turn within a chart session. |
| Verification system | Source-attribution check + 4 deterministic rules (active-status, blank-vs-negative, trend-needs-two-sources, cross-patient-rejection). |
| Observability | Langfuse traces with trace_id, tool latency, token count, verification status. OpenEMR audit row per turn. |
| Evaluation | 5 cases run via a single Python command, JSON output, README-pasteable summary. |
| Deployed | If Railway sidecar comes up: deployed. Else local demo + note that Sunday Final adds Railway deploy. |
| Demo video | 3–5 min walking deployed URL → panel → brief → follow-up → trace → eval output → tradeoff. |

**Status:** Panel + pre-room + **What changed?** wired in JS (**DONE**). Deployed URL + video (**OUTSTANDING**). Local demo path (**DONE**).

### Sunday (Final) — bring it to defensible

Adds: medication/allergy follow-up, recent-abnormal-labs follow-up, preventive-care surface (immunizations only), 10+ eval cases including prompt-injection and authorization-boundary, refined verifier (stale-data labeling, conflict surfacing), feedback buttons writing to Langfuse, AI cost analysis at 100/1K/10K/100K users, deployed agent service on Railway, social post.

**Status:** **DEFERRED** (unchanged).

### Explicitly deferred to v2

Note RAG, vector DB, DDI checking, write-back, nurse/resident roles, break-the-glass, full SMART app launch, prefetch-across-schedule.

## 6. Validated extension points (use these exact names)

Confirmed by direct code reading. **Don't paraphrase — these are the literal handles to grab.**

| Need | Use |
|---|---|
| Module bootstrap | `interface/modules/custom_modules/oe-module-clinical-copilot/openemr.bootstrap.php` (mirror `oe-module-dashboard-context`) |
| Patient panel injection | Listen on `OpenEMR\Events\PatientDemographics\RenderEvent::EVENT_SECTION_LIST_RENDER_AFTER`. `$event->getPid()` gives the active patient. |
| Navbar/header chip (optional) | `OpenEMR\Events\UserInterface\PageHeadingRenderEvent::EVENT_PAGE_HEADING_RENDER`, then `$event->appendTitleNavContent($html)`. |
| REST endpoint for the agent | `OpenEMR\Events\RestApiExtend\RestApiCreateEvent::EVENT_HANDLE` → call `$event->addToRouteMap("POST /clinical-copilot/brief", $handler)`. |
| Twig template path | `OpenEMR\Events\Core\TwigEnvironmentEvent::EVENT_CREATED` → `$loader->prependPath($modulePath . '/templates/')`. |
| Active patient (server side) | `SessionWrapperFactory::getInstance()->getActiveSession()->get('pid')`. Encounter: `->get('encounter')`. **Never trust client-supplied pid.** |
| ACL check | `OpenEMR\Common\Acl\AclMain::aclCheckCore('patients', 'med')` etc. |
| CSRF check | `OpenEMR\Common\Csrf\CsrfUtils::checkCsrfInput(INPUT_POST, subject: 'ClinicalCopilot', dieOnFail: true)`. |
| Same-session API auth | Header `APICSRFTOKEN`; verified by `LocalApiAuthorizationController` via `CsrfUtils::verifyCsrfToken($token, $session, 'api')`. |
| Audit row | `OpenEMR\Common\Logging\EventAuditLogger` — log one `agent_turn` event per request. |
| Output escaping in templates | `text()`, `attr()`, `xlt()`, `xla()`, `js_escape()` (composer-autoloaded globals). |

**Status:** Module bootstrap + demographics hook + gateway CSRF/ACL (**DONE**). Optional REST route + Twig panel path (**OUTSTANDING** / plan allowed `public/api/brief.php` — implemented as standalone PHP).

## 7. Build order — vertical slices, not phases

Each slice ends with something working end-to-end, so a partial day still leaves a demo-able state.

### Slice A — module shell renders in chart (target: 1.5 hr)

- Create `interface/modules/custom_modules/oe-module-clinical-copilot/` mirroring `oe-module-dashboard-context` structure (composer.json, openemr.bootstrap.php, src/Bootstrap.php, templates/, public/assets/).
- Subscribe `Bootstrap` to `PatientDemographics\RenderEvent::EVENT_SECTION_LIST_RENDER_AFTER`. Inject a Twig-rendered placeholder card with text "Co-Pilot loading…" and the patient's pid (via `$event->getPid()`).
- Register module in OpenEMR Modules admin UI; enable it; refresh a demo patient chart and confirm the card renders.
- **Done = card visible inside Farrah Rolle's chart on the deployed URL.**

**Status:** **DONE** for structure + chart injection + loading UI (implemented via `PanelController` inline HTML rather than Twig). **OUTSTANDING:** confirm on **deployed** URL with named demo patient; agent verified locally (e.g. pid=1).

### Slice B — gateway endpoint with security boundary (target: 1.5 hr)

- Add `public/api/brief.php` inside the module (or, if there's time, route via `RestApiCreateEvent`).
- Endpoint contract:
  - Requires authenticated session (include `interface/globals.php`).
  - Reads pid/encounter from `SessionWrapperFactory`, not the request body.
  - Validates `APICSRFTOKEN` header via `CsrfUtils`.
  - `AclMain::aclCheckCore('patients', 'med')` — denies otherwise.
  - Returns 400 if no active patient; 403 on ACL/CSRF failure with no exception text.
  - Generates a `trace_id` (UUIDv4) per request and includes it in the response.
- Module JS calls this endpoint on chart load; renders pid + trace_id in the card to prove the loop works.
- **Done = card shows server-confirmed pid + trace_id, denials work in incognito tests.**

**Status:** **DONE** for endpoint + trace_id + UI chip + POST with CSRF token form pattern per agent. **OUTSTANDING:** full incognito denial matrix documented / re-run on production URL if CSRF mechanism differs from local.

### Slice C — three source-packet builders (target: 2 hr)

- `src/SourcePackets/PacketBuilder.php` interface.
- Three concrete builders, each calling the matching OpenEMR service (no SQL):
  - `IdentityPacketBuilder` → `PatientService::getOne($puuid)` → emits 1 packet (name, age, sex, preferred name).
  - `ActiveProblemsPacketBuilder` → `ConditionService` filtered to active → 0..N packets.
  - `ActiveMedicationsPacketBuilder` → `MedicationService` + `PrescriptionService`, preserves `source_table`, flags duplicates → 0..N packets.
- Packet shape per [Architecture.md "Source Packet Contract"](Architecture.md#source-packet-contract). Add `freshness` enum: `recent | stale | unknown`.
- Gateway endpoint now returns the packet array (still no LLM).
- **Done = browser sees JSON of 5–15 real packets for a demo patient, all carrying `patient_uuid` and source identifiers.**

**Status:** **DONE** per agent (multi-packet JSON including verified path when sidecar up; fallback when sidecar unset).

### Slice D — sidecar skeleton (target: 1.5 hr)

- New folder `agent/copilot-api/` with `pyproject.toml` (FastAPI, anthropic, pydantic, langfuse, pytest).
- `app/main.py` — `/healthz`, `POST /v1/brief`.
- `app/schemas.py` — Pydantic for `BriefRequest`, `SourcePacket`, `LLMOutput`, `VerifiedResponse`. Pydantic validation IS the schema layer; no hand-rolled JSON parsing.
- `app/llm.py` — Anthropic SDK call to `claude-sonnet-4-6` with structured output (tool-use forced JSON). Use prompt caching on the system + verifier-rules block.
- `app/orchestrator.py` — receives gateway request, builds the prompt from packets, calls `app/llm.py`, hands result to verifier.
- Auth: header `X-Copilot-Gateway-Secret` (env var `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET`). Reject anything else.
- Gateway PHP calls sidecar via `Guzzle` → POSTs `{packets, trace_id, patient_uuid, use_case}` → returns sidecar response.
- **Done = clicking the panel produces a real LLM response (unverified) on screen.**

**Status:** **DONE** for codebase + local wiring. **OUTSTANDING:** production secret management + reachable base URL from Railway OpenEMR service.

### Slice E — verifier (target: 2 hr) ← **the load-bearing piece**

- `app/verifier.py`. Rules in priority order:
  1. **Schema valid:** Pydantic must parse `LLMOutput`. Otherwise repair-once, then strip.
  2. **Source attribution:** every `claim.source_ids` must be non-empty and each ID must exist in this turn's packet set.
  3. **Patient binding:** every cited packet's `patient_uuid` must equal the request's `patient_uuid`. Failure = drop claim + log security event.
  4. **Active-status rule:** any claim using "current/active/on" for a medication or "has" for a condition requires a packet with `status == 'active'`.
  5. **Trend rule:** `claim_type == 'trend'` requires ≥2 source IDs with comparable values.
  6. **Blank-vs-negative:** claims like "no allergies" or "no contact preference" require an explicit negative source value (e.g., NKDA marker), not absence.
  7. **Cross-patient:** drop and log if any cited source isn't in the request's packet set.
  8. **Refusal scope:** drop any claim that recommends diagnosis, prescribes, orders, or writes.
- On failure: try one repair (send Claude the verifier errors + ask for a fixed JSON). If still failing, drop unsupported claims and render only the verified subset with an explicit "I couldn't verify X — open the [section] panel" line.
- **Done = unit tests in `agent/copilot-api/tests/test_verifier.py` cover all 8 rules with passing + failing cases.**

**Status:** **DONE** for verifier implementation + eval-driven coverage (5/5). **OUTSTANDING:** dedicated **pytest** suite as specified (`tests/test_verifier.py` + related files).

### Slice F — observability (target: 1 hr)

- Wrap orchestrator + verifier with Langfuse spans (`@observe()` decorators or manual). Capture: trace_id, model, prompt template version (`v1`), tool/packet counts, LLM latency, token in/out, verifier status, unsupported-claim count.
- PHI policy: `patient_uuid` hashed (SHA256 first 12 chars) in trace metadata. No raw notes. No raw model output stored unless `COPILOT_ENV=dev`.
- OpenEMR side: gateway writes one `EventAuditLogger` row per turn with `{event: 'agent_turn', user, pid, trace_id, source_ids, verifier_status, denial_reason?}`.
- **Done = a single chart click produces a Langfuse trace AND an `audit_master` row, joinable by trace_id.**

**Status:** **DONE** per agent report locally. **OUTSTANDING:** verify Langfuse project receives traces from **production** sidecar + confirm DB audit query on deployed DB.

### Slice G — eval framework (target: 1.5 hr)

- `agent/copilot-api/evals/` with `cases/*.json` (one file per case) and `runner.py`.
- Each case: `{name, packets: [...], request: {...}, expectations: {...}}` where expectations is one of: `must_cite_all_of`, `must_not_claim_active`, `must_state_missing`, `must_reject`, `must_drop_claim_about`.
- 5 cases for Thursday: A1c trend, missing allergies (must say "not retrieved" not "no allergies"), stale meds (must label stale), cross-patient (must reject), unsupported claim repair.
- Runner: `python -m evals.runner` → prints table + writes `eval_results.json`.
- **Done = `python -m evals.runner` prints 5/5 pass.**

**Status:** **DONE** for runner + 5 passing cases + `eval_results.json`. **OUTSTANDING:** optional parity with named “stale meds” scenario (see snapshot).

### Slice H — deploy + demo (target: 1.5 hr)

- Build sidecar Dockerfile (Python 3.12 + uv).
- Add `copilot-api` Railway service (Docker Image or build-from-repo with `agent/copilot-api/` as root).
- Env vars on `copilot-api`: `ANTHROPIC_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET`, `COPILOT_ENV=production`.
- On `openemr` service add: `COPILOT_API_BASE_URL=http://${{copilot-api.RAILWAY_PRIVATE_DOMAIN}}:8000`, `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<same>`.
- Ensure `copilot-api` has **no public domain**.
- Smoke test: incognito → demo patient → panel renders verified brief → Langfuse shows trace.
- Record demo video (Loom, 3–5 min) and put URL in README.
- **Done = deployed URL works end-to-end.**

**Status:** **DONE** for Dockerfile + README/env documentation. **OUTSTANDING:** Railway service creation, secrets, private networking smoke, demo video URL, root/deployed README links.

### Sunday additions (Slices I–L)

- **I:** Medication/allergy follow-up tool + recent-abnormal-labs tool + preventive-care (immunizations) packet builder.
- **J:** Verifier rules: stale-data labeling (>90d med, >180d lab); conflict surfacing for `lists` vs `prescriptions` duplicates.
- **K:** 5 more eval cases: duplicate medication, sensitive-encounter respect, prompt-injection inside note text (note-text isn't fetched in v1, so synthesize a packet with injection text), latency p95 under budget, allergy-conflict surfacing.
- **L:** Feedback buttons (Helpful / Missing data / Incorrect / Too slow / Source unclear) → POST to gateway → Langfuse score event. AI cost analysis doc (`planning/cost_analysis.md`) at 100 / 1K / 10K / 100K users with architecture deltas at each tier.

**Status:** **DONE** (2026-05-01). All four sub-slices shipped; see [AgDR-0008](../agentdocs/decisions/AgDR-0008-sunday-slices-i-through-l.md) and the 2026-05-01T22:00Z snapshot above. Pytest 24/24, evals 11/11.

## 8. File inventory (concrete paths)

Below, **DONE** = present / substituted; **OUTSTANDING** = not shipped.

### OpenEMR module (PHP)

```
openemr/interface/modules/custom_modules/oe-module-clinical-copilot/
├── composer.json                                  # DONE — PSR-4: OpenEMR\Modules\ClinicalCopilot\
├── openemr.bootstrap.php                          # DONE — mirrors oe-module-dashboard-context
├── info.txt                                       # DONE
├── version.php                                    # DONE
├── src/
│   ├── Bootstrap.php                              # DONE — event subscriptions
│   ├── Controller/
│   │   └── BriefController.php                    # OUTSTANDING (plan name); PanelController.php DONE instead
│   ├── Gateway/
│   │   ├── BriefGateway.php                       # OUTSTANDING (logic largely in brief.php + helpers)
│   │   ├── TaskToken.php                          # DONE — 15-min HMAC token (patient_uuid, user_id, encounter_uuid, scope, exp)
│   │   └── SidecarClient.php                      # DONE — Guzzle POST to copilot-api
│   ├── SourcePackets/
│   │   ├── PacketBuilder.php                      # DONE — interface
│   │   ├── PacketDto.php                          # DONE — readonly value object
│   │   ├── IdentityPacketBuilder.php              # DONE
│   │   ├── ActiveProblemsPacketBuilder.php        # DONE
│   │   ├── ActiveMedicationsPacketBuilder.php    # DONE
│   │   ├── AllergiesPacketBuilder.php             # DEFERRED Sunday
│   │   ├── RecentLabsPacketBuilder.php            # DEFERRED Sunday
│   │   └── ImmunizationsPacketBuilder.php         # DEFERRED Sunday
│   └── Audit/
│       └── AgentTurnAuditor.php                   # DONE — writes audit row
├── public/
│   ├── api/brief.php                              # DONE — endpoint that wires Gateway → Sidecar
│   └── api/feedback.php                           # DEFERRED Sunday
├── templates/
│   └── panel.html.twig                            # OUTSTANDING — panel inlined in PanelController
└── public/assets/
    ├── js/copilot.js                              # DONE — fetch brief, render claims, source chips
    └── css/copilot.css                            # DONE
```

### Sidecar (Python)

```
agent/copilot-api/
├── pyproject.toml                                 # DONE — fastapi, anthropic, pydantic v2, langfuse, httpx, pytest
├── Dockerfile                                     # DONE
├── app/
│   ├── main.py                                    # DONE — FastAPI app, /healthz, POST /v1/brief (follow-ups via use_case body field)
│   ├── schemas.py                                 # DONE — Pydantic models (single source of truth)
│   ├── auth.py                                    # DONE — X-Copilot-Gateway-Secret check
│   ├── orchestrator.py                            # DONE — builds prompt from packets, dispatches LLM
│   ├── llm.py                                     # DONE — Anthropic client, prompt caching, structured output
│   ├── verifier.py                                # DONE — 8 rules, repair-once loop
│   ├── rendering.py                               # OUTSTANDING — display contract may live in PHP/JS instead
│   ├── observability.py                           # DONE — Langfuse spans, PHI redaction
│   └── prompts/
│       └── brief_v1.txt                           # DONE — versioned prompt template
├── tests/
│   ├── test_schemas.py                             # OUTSTANDING
│   ├── test_verifier.py                           # OUTSTANDING — all 8 rules
│   └── test_orchestrator.py                       # OUTSTANDING
└── evals/
    ├── runner.py                                  # DONE
    ├── cases/                                     # DONE — JSON per case
    └── README.md                                  # DONE
```

## 9. Verifier contract (the LLM must produce this)

```json
{
  "answer_type": "pre_room_brief | follow_up | refusal",
  "claims": [
    {
      "text": "string (rendered to physician verbatim)",
      "claim_type": "fact | trend | absence | conflict",
      "source_ids": ["packet:source:id", "..."],
      "caveat": "string | null"
    }
  ],
  "missing_data": ["string"],
  "refusals": ["string"],
  "suggested_followups": ["What changed?", "Medication check"]
}
```

Rendering rule: the UI renders **only verified claims**. Unsupported/dropped claims become a `missing_data` line. Free-form prose outside this schema is rejected at parse time.

## 10. Observability + audit (the join key)

`trace_id` is generated in PHP at the gateway, sent to the sidecar in the request body, included in every Langfuse span, and written to the OpenEMR `audit_master` row. Anyone investigating an incident can pivot from one to the other in one query. **This single decision is the difference between debuggable and not.**

## 11. Risks (only the ones with non-obvious mitigations)

| Risk | Mitigation |
|---|---|
| Demo data is too thin (no recent labs, no abnormal flags on demo patients) | Pre-stage 1–2 demo rows via SQL on the deployed DB before recording. Document in README that this is demo augmentation. **Status:** **OUTSTANDING** before polished video. |
| Module ACL/event registration is fiddlier than expected | Slice A is intentionally first and isolated. If event hook is slow, fall back to direct include from `interface/patient_file/summary/demographics.php` via a sites-customization include — uglier but works. |
| Sidecar Railway deploy hits networking issues at 23:00 CT | Have a local-only demo recorded as a backup video before attempting deploy. Submit local demo + "Railway deploy in progress" note if needed. **Status:** aligns with current **OUTSTANDING** deploy. |
| Verifier is too strict and the demo shows nothing | Pre-record one good run on a tested patient. Verifier strictness is the **feature** — defend it. |
| LLM JSON occasionally invalid | Repair-once is built in. Use Anthropic tool-use mode (forces JSON) not freeform text. |
| Token cost explodes on a long context | Cap source packets at 50/turn. Truncate `display` to 200 chars per packet. Use prompt caching on the system + rules block. |

## 12. Verification (how to test before declaring done)

End-to-end Thursday smoke test:

1. Open deployed Railway URL in incognito → log in as `admin`. **OUTSTANDING** (local **DONE** per agent).
2. Open Farrah Rolle's chart → panel renders within 5 seconds. **PARTIAL** — chart verified locally; named patient / deployed **OUTSTANDING**.
3. Brief shows ≥3 cited claims with source chips. **DONE** when sidecar + LLM available; fallback path exercised otherwise.
4. Click a source chip → opens the underlying chart record (or shows the packet). **OUTSTANDING** — chips render; deep-link behavior unconfirmed from transcript.
5. Click `What changed?` → sidecar handles a follow-up turn within 5 seconds. **DONE** in UI wiring; **OUTSTANDING** full timing/sidecar test on deploy.
6. Open Langfuse → find the trace by trace_id; tool spans + token counts visible. **OUTSTANDING** on cloud project until sidecar deployed with keys.
7. Open phpMyAdmin / DB UI → `SELECT * FROM audit_master WHERE event = 'agent_turn' ORDER BY date DESC LIMIT 5` → row exists with matching trace_id. **DONE** locally per agent; **OUTSTANDING** on Railway DB.
8. Run `python -m evals.runner` from `agent/copilot-api/` → 5/5 pass. **DONE** per agent.
9. Try forging a request with a different `pid` → returns 403, audit row logs denial. **OUTSTANDING** explicit adversarial test documented.

If 1–9 all pass, Thursday submission is real. If 6, 7, or 8 fail, the agent isn't observable/auditable/measurable and Thursday should ship with explicit gaps documented.

## 13. Submission deliverables (don't forget)

- **Repo `royharden/openemr`:** all module + sidecar code committed; root `AUDIT.md`, `USERS.md` (+ stub `USER.md`), `ARCHITECTURE.md`. Commit messages follow Conventional Commits with `Assisted-by: Claude Code` trailer per [openemr/CLAUDE.md](../CLAUDE.md). **OUTSTANDING:** confirm commit scope + root doc filenames vs `planning/` moves.
- **README:** deployed URL, login note, deliverable links. **PARTIAL** — module/sidecar READMEs **DONE**; root marketing README **OUTSTANDING**.
- **Demo video (3–5 min):** opens with the deployed URL on screen; shows the panel, a verification failure, a trace, and an eval run. **OUTSTANDING**.
- **Eval dataset + results:** in `agent/copilot-api/evals/` with a JSON results artifact. **DONE** (`eval_results.json` + cases).
- **AI Cost Analysis (Sunday):** `planning/cost_analysis.md`. Real dev spend + projected at 100/1K/10K/100K users with architecture deltas (caching, batch, scaling) at each tier. **DEFERRED** Sunday.
- **Social post (Final only):** drafted Sunday morning. **DEFERRED**.

## 14. Out of scope for this plan (won't address)

- BAA negotiation, real production hosting plan, full SMART app launch, role-based variants, drug-drug interactions, note RAG, vector DB, write-back. All flagged in [Architecture.md "Build Roadmap"](Architecture.md#build-roadmap) for v2.

---

**One-line thesis to defend:** *I'm shipping the smallest version of a clinical agent that is honest about what it knows and what it doesn't — read-only, current-patient, source-cited, verifier-gated, observable, and deployed — because in a clinical context the trustworthy 30% beats the impressive 80%.*

**Status note:** “Deployed” portion of the thesis remains **OUTSTANDING** until Railway sidecar + env wiring + deployed smoke complete.
