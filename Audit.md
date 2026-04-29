# AUDIT.md — OpenEMR Audit for Clinical Co-Pilot Integration (v2)

> **v2 changelog vs [v1](./Claude_Audit.md):** Stronger code-grounded evidence (named service classes: `PrescriptionService`, `ObservationLabService`, `ListService`, `RestConfig::request_authorization_check`). Corrected lab-join chain to 5 tables (was 3). Added Finding D5 (patient demographic blanks ≠ negative facts). Added Finding C5 (breach-investigation reconstructability). Added explicit observability findings section. Added "Audit Impact on Architecture" trace. Sidecar-no-DB-credentials elevated to its own finding.
>
> Companion docs: [Claude_Users_v2.md](./Claude_Users_v2.md) (the user this agent serves) and [Claude_Architecture_v2.md](./Claude_Architecture_v2.md) (how these findings shape the architecture).
>
> **Scope:** OpenEMR forked from `github.com/openemr/openemr`, running locally with demo patient data, deployed to Railway. Covers the five categories required by the case study: security, performance, architecture, data quality, compliance.

---

## One-Page Summary (~500 words)

OpenEMR is a credible foundation for the Clinical Co-Pilot. It is ONC-certified, has 20+ years of evolution, and ships with the parts an AI assistant should not reinvent: an EHR data model, REST and FHIR R4 surfaces, OAuth2 + SMART on FHIR, a centralized `AclMain` ACL engine, an `EventAuditLogger` running on a separate DB connection, and a custom-module extension path.

**Top finding — the trust model is OpenEMR's strongest asset, not its weakness.** The OAuth2 + SMART + `AclMain` + `EventAuditLogger` stack is layered, hardened, and proven. The agent must integrate *through* this stack, not around it. Doing so means inheriting 20 years of authorization work; bypassing it means re-implementing all of it under sprint pressure. Every decision in [Claude_Architecture_v2.md](./Claude_Architecture_v2.md) — FHIR/REST instead of direct SQL, scoped task tokens, audit-log integration — flows from this finding.

**Second finding — the failure mode this audit exists to prevent is the agent becoming a shadow EHR.** If the Python sidecar holds MariaDB credentials, or if a broad reusable OAuth scope is used, or if the `patient_uuid` for tool calls comes from the model rather than the chart context, the agent quietly becomes a second access path with weaker authorization than the primary system. Mitigation: the sidecar holds **no DB credentials**, every tool call carries a server-supplied `patient_uuid`, the gateway issues a 15-minute task token bound to `(user, patient, encounter, purpose_of_use)`, and tools fail closed.

**Third finding — there is a real authorization gap to mitigate, not inherit.** Spot-checks of the FHIR controllers indicate that some endpoints gate primarily on OAuth scope rather than re-checking `AclMain` for the specific user-patient relationship. A token with `user/Patient.rs` says "this token can read Patient resources" but doesn't enforce "*my* patients vs. *any* patients." Konstantin identified this independently in the peer defense; the architecture's task-token gateway is the answer.

**Fourth finding — data quality is the dominant agent-failure mode, not security.** Five patterns will break a naïve agent: (1) `lists` is polymorphic and contains both active and historical entries indistinguishably without explicit filtering on `activity = 1` and `enddate IS NULL`; (2) medication data is split between `prescriptions` and `lists_medication` and `PrescriptionService` explicitly unions them with overlapping rows; (3) `prescriptions.drug` is free text — same drug appears as "Metformin 500mg," "metformin," "METFORMIN HCL 500MG TABLET"; (4) `procedure_result.result_code` (LOINC) is often blank; (5) **`patient_data` defaults many demographic fields to empty strings — blank is not the same as a negative fact.** An agent that treats blanks as negatives produces clinically wrong summaries.

**Fifth finding — observability is greenfield and is required from day 1.** OpenEMR's `EventAuditLogger` is a strong HIPAA foundation but logs at the API-call level, not the agent-turn level. For a synthesizing agent, that's insufficient. The architecture wires Langfuse for engineering-grade traces and writes a single "agent_turn" event per turn for compliance auditability. Per Ash's lecture: observability is not optional.

**Sixth finding — deployment defaults are the soft underbelly.** Default credentials (`admin` / `pass`), audit-logging globals that can be silently disabled, encryption keys stored in `sites/<site>/documents/`, and PHP `display_errors` defaults are all deployment-runbook items. None are blockers; all belong in the runbook.

**Bottom line:** OpenEMR is a solid foundation. Risks are manageable with deliberate architecture decisions. None are blockers if addressed proactively.

---

## 1. Security Audit

### CRITICAL — S1: Default Administrator Credentials

OpenEMR ships with `admin` / `pass`. Consistently top-3 cause of healthcare data breaches.

**Evidence:** `openemr/CLAUDE.md`, `openemr/CONTRIBUTING.md`, `sql/example_patient_users.sql`. **Action:** rotate before deployment; enforce via Railway env-var injection. **Architecture response:** documented in deployment README.

### CRITICAL — S2: Sidecar Must NOT Have Database Credentials

A Python sidecar with direct MariaDB access becomes a shadow EHR with its own permission system. Tool bugs would bypass `AclMain`, sensitivity flags, and patient binding. Database credentials in another service also expand the blast radius.

**Architecture response:** the sidecar holds zero DB credentials. All clinical data access flows through the gateway → OpenEMR FHIR/REST. MariaDB is private on Railway. This is the single most important security tradeoff in the architecture.

### CRITICAL — S3: Agent Authorization Must Be Narrower Than Generic API Access

OpenEMR's REST and FHIR routes have authorization checks (e.g., `RestConfig::request_authorization_check(...)` in `apis/routes/_rest_routes_standard.inc.php`; the FHIR routes in `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php` include patient-binding behavior for patient-role requests). That is a useful baseline but it is not enough for an AI assistant that chains tools and synthesizes across resources.

Risks specific to the agent:
- Chained tool calls aren't a single API request.
- A broad OAuth scope or reusable sidecar token becomes a privilege-escalation path.
- Category-level authorization does not express "this exact physician, this exact patient, this exact visit, this exact purpose."

**Architecture response:** the gateway mints a 15-minute task token bound to `(user, patient, encounter, purpose_of_use)`. The `patient_uuid` for every tool call is server-supplied, never model-controlled. Cross-patient tool arguments are rejected before the tool runs. Both successful and denied requests are audited.

### HIGH — S4: Two Parallel Authorization Surfaces

OpenEMR has two authorization systems running in parallel: GACL (session-cookie-based, for the legacy web UI) and OAuth2 + SMART on FHIR (token-based, for REST/FHIR). Both well-implemented individually, but independent. A user with limited GACL permissions can hold a broader OAuth scope, or vice versa.

**Evidence:** `src/RestControllers/AuthorizationController.php`, `src/RestControllers/Authorization/BearerTokenAuthorizationStrategy.php`, `src/RestControllers/Authorization/LocalApiAuthorizationController.php`. **Architecture response:** the gateway re-verifies session and re-checks ACL before minting a task token; both surfaces are aligned at the agent boundary.

### HIGH — S5: FHIR Endpoint Scope-Only Checks

Spot-checks of FHIR controllers indicate OAuth scope alone is sometimes the only gate — `AclMain` is not always re-checked for the specific user-patient relationship. A broad OAuth token can expose API data the same user could not see via the UI. Konstantin identified this independently in the peer defense.

**Architecture response:** task-token gateway with explicit patient-context binding — see [Architecture §Authorization](./Claude_Architecture_v2.md#authorization--trust-boundaries).

### HIGH — S6: Legacy SQL String Concatenation

`library/` contains older PHP code that in some places constructs SQL by string concatenation. Modern code in `src/` uses `QueryUtils` correctly, but the boundary is not enforced.

**Verification:** `grep -r "SELECT.*\$_GET\|SELECT.*\$_POST" library/` — any result is a finding. **Architecture response:** the agent never calls `library/` functions. All data access goes through FHIR R4 / Standard REST endpoints.

### HIGH — S7: PHI Leakage Surfaces (Logs, Traces, URLs, Prompts, Errors)

The agent introduces new places where PHI can appear: model prompts, observability traces, error logs, request bodies, tool outputs, eval artifacts. Observability tooling can quietly become a PHI store.

**Architecture response:**
- Patient UUIDs hashed in traces; no raw patient names.
- Default trace contents: source IDs, tool names, timings, verifier results — *not* raw prompts or notes.
- Full prompt logging gated to demo data or self-hosted Langfuse under BAA.
- PHP `display_errors` off in deployed environments.

### HIGH — S8: Prompt Injection in Chart Text

Future unstructured note retrieval will surface text that may contain instructions ("ignore prior instructions and...").

**Architecture response:** v1 uses structured data only; chart text is treated as data, never as instructions. When note retrieval lands in v2, notes will be wrapped in explicit data containers and the eval suite will include prompt-injection cases before the feature ships.

### MEDIUM — S9: Three Coexisting Template Engines

OpenEMR uses Twig, Smarty, and raw PHP templates with different default escaping. **Architecture response:** the agent module uses Twig only, all rendered claim strings are escaped at the template layer, and the verifier strips HTML/JS before render.

### MEDIUM — S10: Encryption Keys on Local Filesystem

Keys live in `sites/<site>/documents/` by default — same disk as the data. Real production should back this with a KMS. Out of scope for this assignment; documented as deployment-hardening.

### MEDIUM — S11: Session Token Expiry

OpenEMR sessions persist as long as the browser is open. **Architecture response:** the agent's task token has its own 15-minute lifetime, independent of OpenEMR session.

### LOW — S12: PHI in URL Parameters (Legacy Endpoints)

Some legacy endpoints pass patient IDs as URL query parameters (`?pid=42`). URLs are logged. Modern endpoints use UUIDs in path segments. **Architecture response:** the agent uses only modern UUID-based FHIR endpoints.

### Common Web Vulnerabilities — Generally Well Handled

- ✅ HTML escaping via `laminas/laminas-escaper` and `htmlpurifier`.
- ✅ CSRF protection at `OpenEMR\Common\Csrf\*`.
- ✅ MFA via `robthree/twofactorauth`.
- ✅ Password hashing via `password_hash`/`password_verify` in `OpenEMR\Common\Auth\AuthHash`.

---

## 2. Performance Audit

### Database, Not PHP, Is the Bottleneck

OpenEMR is a PHP-FPM monolith fronting MariaDB. PHP execution is fast enough that database queries dominate latency.

### CRITICAL — P1: 90-Second Workflow Requires Bounded Retrieval

The physician does not need the whole chart before entering the room. The agent should not fetch it.

**Architecture response:** Tier-1 prefetch with bounded defaults — last 5 encounters, last 3 vitals, last 6 months OR last 20 labs, active records only. "Go deeper" is an explicit user action, not a default.

### HIGH — P2: FHIR Calls Are Not Lightweight

Each FHIR resource read involves: `AclMain` check → service-layer call → multi-table JOIN → FHIR mapping → JSON serialization. Realistic budget: **100–500ms** per uncomplicated FHIR call on a warm DB. Cold cache or large patient histories run worse.

**Architecture response:** Tier-1 tools fired in parallel; Redis cache (5-min TTL); briefing target <3s.

### HIGH — P3: Lab Retrieval Is a 5-Table Join

`ObservationLabService` joins `procedure_result`, `procedure_report`, `procedure_order`, `procedure_order_code`, and `patient_data`. Slowest tool the agent makes.

**Architecture response:** lab tool is Tier-2 (on-demand only), UI shows a loading indicator on first invocation per session, results cached for the chart session.

### HIGH — P4: Medication Reconciliation Has Built-In Complexity

`PrescriptionService` explicitly unions data from `prescriptions` and `lists`. Records may differ on active status, source table, RxNorm availability, dosage fields.

**Architecture response:**
- Source packet preserves `source_table` for every medication entry.
- Active medications preferred; duplicates flagged, not auto-resolved.
- Verifier rule: "active" claims require `status=active` in source; otherwise blocked.
- Eval suite has dedicated duplicate-medication cases.

### HIGH — P5: `lists` Index Mismatch

`lists` is indexed on `(pid, type, activity)`. Queries filtered only by `pid` scan more rows than expected. **Architecture response:** every list-table query includes the type filter.

### MEDIUM — P6: `patient_data` Is Wide

~170 columns. Heavy reads pull a lot of unused data. **Architecture response:** the FHIR `Patient` resource returns only the needed fields.

### MEDIUM — P7: Patient Lookup by Name

UUID lookup is indexed; name lookup is a full table scan. **Architecture response:** the agent always resolves UUID from the chart context, never searches by name.

### MEDIUM — P8: Encounter History Grows Unboundedly

`form_encounter` has no inherent bound. **Architecture response:** `get_recent_encounters` is paginated (`LIMIT 5 ORDER BY date DESC` by default).

### MEDIUM — P9: No Application-Level Query Cache

OpenEMR has no built-in query cache. **Architecture response:** Redis cache layer in the agent sidecar (not in OpenEMR).

### MEDIUM — P10: Concurrent User Scaling

PHP-FPM is synchronous. At 300 concurrent users making 2–3 API calls each, that's ~900 concurrent processes. Within range for well-configured hardware but requires horizontal scaling beyond ~100 concurrent users.

### MEDIUM (demo) / HIGH (production) — P11: Railway Is Fast to Ship, Not a Scale Plan

Railway clears the bar for demo data + sprint speed. It is not the answer for a 500-bed hospital with real PHI. **Architecture response:** services kept stateless except MariaDB and Redis; sidecar private; config in env vars; migration path to BAA-covered cloud documented in deployment README.

---

## 3. Architecture Audit

### POSITIVE — A1: OpenEMR Provides Good Extension Points

Useful integration points the agent uses:

- `interface/modules/custom_modules/` — custom-module path
- `apis/routes/_rest_routes_standard.inc.php` — REST routes
- `apis/routes/_rest_routes_fhir_r4_us_core_3_1_0.inc.php` — FHIR R4 routes
- `src/RestControllers/` — REST controllers
- `src/Services/` — data-access services
- `src/Common/Logging/EventAuditLogger.php` — audit logging
- `src/Events/RestApiExtend/RestApiCreateEvent.php` — REST extension events for modules

**Implication:** the agent integrates without forking the chart UI or inventing a new EHR.

### HIGH — A2: Two Parallel Code Styles

- **Modern (`src/`):** PSR-4, dependency-injected, typed (PHPStan level 10), tested.
- **Legacy (`library/` and `interface/`):** procedural PHP, `$_SESSION`/`$GLOBALS` as service locators, untyped, classmap-autoloaded.

**Architecture response:** the agent module lives in `interface/modules/custom_modules/oe-module-clinical-copilot/` for module conventions, but its server-side logic calls only `src/` services and FHIR endpoints. Zero `library/` calls. Hard rule.

### HIGH — A3: Audit Logging Exists But Needs Agent Context

`EventAuditLogger` (separate DB connection — resilient to transaction rollback) supports audit events. `api_log` stores method, request URL, body, response, user, and patient references at the API-call level.

Gap: an agent turn synthesizes multiple records. "GET /api/patient/{uuid}/medication" is insufficient.

**Architecture response:** one logical "agent_turn" event per turn carrying:
- `trace_id`
- use case
- purpose of use
- patient UUID
- tool names called
- source IDs returned
- verification status (pass / repaired / failed)
- denied request reason (when applicable)

**Hardening note:** audit logging is toggleable via globals (`enable_auditlog`, `audit_events_*`). A misconfigured deployment can silently disable PHI access logging. Must be enforced on at deployment.

### MEDIUM — A4: FHIR Is Useful But Not Sufficient Alone

FHIR R4 + US Core covers Patient, Encounter, Observation, Condition, MedicationRequest, AllergyIntolerance, Immunization, DocumentReference. OpenEMR-specific workflow data (e.g., prescription fill history with OpenEMR-specific fields) lives outside FHIR abstractions.

**Architecture response:** FHIR for normalized resources; Standard REST for OpenEMR-specific workflow data; both normalized into the same source-packet contract.

### MEDIUM — A5: No Existing AI/ML Layer

Greenfield. No prior LLM integration patterns to follow, but no technical debt to work around. **Architecture response:** keep AI code isolated in the module + sidecar; explicit source-packet and verifier contracts; evals from day one.

### Multi-Site / Multi-Tenant Awareness

OpenEMR supports multi-tenant via `sites/<site_name>/`. URLs are tenant-scoped (`/apis/default/...` vs `/apis/alternate/...`). **Architecture response:** the agent module reads launching site from the bearer token / session; never hardcodes `default`.

### Symfony EventDispatcher

OpenEMR uses Symfony EventDispatcher for clean extension without monkey-patching. The module registers handlers for chart-edit events to invalidate Redis cache.

---

## 4. Data Quality Audit

Data quality is the audit category that most directly determines agent reliability. An agent that treats the data as clean will produce clinically wrong summaries.

### HIGH — D1: Active vs. Historical Records in `lists`

`lists` is polymorphic. It includes `activity`, `enddate`, `begdate`, and type fields. `ListService::getAll()` fetches by patient and type ordered by date but the agent must still interpret active/inactive correctly. Without filtering on `activity = 1` and `enddate IS NULL`, queries return resolved diagnoses, past meds, and historical allergies alongside current ones.

**Architecture response:** every tool that hits `lists` filters on active status. Source packet builder includes `activity`, `begdate`, `enddate`, source status. **Verifier rule: "active"/"current" claims without active evidence are stripped.** This is the single most important data-quality safeguard.

### HIGH — D2: Free-Text Medication Names

`prescriptions.drug` is free text. `rxnorm_drugcode` exists but is often blank. `PrescriptionService` explicitly notes that medication-list entries may not have RxNorm codes. "Metformin 500mg," "metformin," and "METFORMIN HCL 500MG TABLET" all refer to the same drug.

**Architecture response:** source-packet builder normalizes drug names for matching (lowercase, strip dosage/units). MVP surfaces meds and flags uncertainty; does not claim drug-interaction completeness. Evaluation suite has explicit cases for the "did she fill her [name]?" use case across name variants.

### HIGH — D3: Lab Results Need Full Metadata

`procedure_result` stores `result_code`, `result_text`, `units`, `result`, `range`, `abnormal`, `comments`, `result_status`. Code coverage and result semantics vary by source.

**Architecture response:**
- Every lab claim includes date, units, source.
- Final results preferred; preliminary/corrected explicitly labeled.
- Abnormal flag and range surfaced when present.
- Falls back to `result_text` when LOINC code is absent.
- Says "no recent result found" rather than inferring normality.

### HIGH — D4: Sensitive Encounters Exist

`form_encounter.sensitivity` field flags mental health, HIV, and substance abuse encounters. Not surfaced to all users by default.

**Architecture response:** the agent inherits OpenEMR's filtering; does not see what the underlying user cannot see. Sensitivity metadata included in source packets. Eval cases cover sensitive-encounter-omission scenarios. **Known v2 gap:** the agent does not currently announce when sensitive data has been filtered.

### MEDIUM — D5: Patient Demographic Blanks ≠ Negative Facts

`patient_data` contains many fields that default to empty strings. Blank fields are *not* the same as negative facts. An agent might state "no contact," "no interpreter needed," or "no consent issue" when the data is merely blank.

**Architecture response:** the source-packet builder distinguishes NULL/empty-string from explicit negative values. The verifier rejects negative claims ("no allergies," "no contact preference") unless backed by an explicit negative source value. Eval suite includes a case for an all-blank-demographics patient — the agent must say "unknown," not invent negatives.

### HIGH — D6: Dual Medication Storage — `prescriptions` and `lists_medication`

Same medication can appear in both with different metadata. `PrescriptionService` unions them. Reconciliation is non-trivial.

**Architecture response:** authoritative source for "active medications" is the FHIR `MedicationRequest` resource; source packet carries the underlying source (`prescriptions` vs `lists_medication`); conflicts surfaced as conflicts, not auto-resolved.

### Free-Text Notes Are Unstructured

`pnotes` and `form_encounter` notes are free text. NLP extraction quality directly impacts any future note-search tool. **Architecture response:** free-text note search **deferred to v2** specifically because the audit identified this as the highest hallucination-risk path.

### Stale Data Is the Norm

Med lists go un-reconciled for months in real practice. **Architecture response:** every source packet carries `last_updated`. Verifier marks claims derived from stale packets. UI shows a stale-data badge.

### Sample Data Is Unrepresentative

`sql/example_patient_data.sql` is small and does not exercise edge cases (missing fields, conflicting notes, partial vitals). **Architecture response:** eval suite includes synthetic patients constructed for these conditions specifically.

---

## 5. Compliance & Regulatory Audit

### CRITICAL — C1: Minimum Necessary Standard

The OAuth2 scope `patient/*.read` grants access to all clinical data — convenient, but violates Minimum Necessary.

**Architecture response:** narrow `user/<resource>.rs` scopes only for resources the agent actually uses. No `system/*`, no write scopes, no `offline_access`. Tool-specific bounded retrieval. No broad patient export. Full scope list in [Architecture §Authorization](./Claude_Architecture_v2.md#authorization--trust-boundaries).

### CRITICAL — C2: BAAs Are Required for Real PHI

For this assignment: per Byron's allowance and case-study brief, we operate under the assumption of a signed BAA with Anthropic and other vendors. **For real production: non-negotiable.** Anthropic, OpenAI, and Google all offer BAAs on enterprise tiers. Railway, the LLM provider, the observability provider, email, backups, and logs may all become business associates.

**Architecture response:** every LLM call logged (request ID, patient UUID, model version, token counts) so disclosure trail is reconstructible. PHI minimized in prompts. Vendor list documented. PHI kept out of nonessential traces. Demo data only for Gauntlet.

### HIGH — C3: De-Identification Is Not Viable

For a patient-context co-pilot, de-identification before the LLM is not viable — the whole point is patient-specific context. The BAA path is the path. Stated explicitly when defending the architecture.

### HIGH — C4: Observability and Audit Are Different Logs

Audit answers "who accessed what and why." Observability answers "what did the agent do and how well did it work." Both are required. A system with only audit logs cannot debug hallucination. A system with only traces cannot satisfy compliance review.

**Architecture response:**
- OpenEMR `EventAuditLogger` for access (compliance grade).
- Langfuse traces for agent behavior (engineering grade).
- Shared `trace_id` for end-to-end reconstruction.
- PHI redacted in traces by default.

### HIGH — C5: Breach Investigation Needs Reconstructable Events

If a patient asks who saw their data, the organization must reconstruct access. A single "agent request" log line is not enough if the agent fetched medications, labs, allergies, and notes within that turn.

**Architecture response:**
- Tool-level access logged.
- Denied requests logged at the same tier as successful requests.
- Source-packet IDs logged.
- User feedback (especially "Incorrect" or "Source unclear") logged.

### HIGH — C6: Retention and Deletion Policies Must Include Agent Artifacts

Agent traces, prompt logs, eval failures, feedback, and source packets may include PHI if not controlled. AI artifacts can become unmanaged medical records or unmanaged PHI stores.

**Architecture response:**
- Avoid storing full prompts/responses in production by default.
- Set explicit retention policy for trace data (default: 90 days for engineering traces; 6 years for audit events per HIPAA).
- Store only source IDs and verifier metadata unless full content is required.
- Align trace retention with organizational compliance policy.

### Data Retention

HIPAA requires audit records for 6 years. OpenEMR doesn't enforce retention itself; deployment choice. The agent does not introduce new patient records (read-only v1). Observability traces follow the same retention as the patient record if they capture PHI.

### ONC Certification

OpenEMR is ONC-certified at Stage III Meaningful Use; Inferno Certification Test runs in CI. **Architecture response:** the agent is a *consumer* of FHIR endpoints, not a modifier — does not register new FHIR resources or change responses. Inferno still passes.

### Break-the-Glass

OpenEMR has no built-in "break the glass" override mechanism. Not a near-term concern — v1 is read-only, scoped to open chart, and rejects mismatched patient UUIDs at the gateway. Flagged for hospital deployment.

### Breach Notification

Out of scope for the codebase; in scope for the deployment runbook. Documented.

---

## 6. Observability Audit

Per Ash's lecture: *"observability is the thing that gives you the key into the black box that is the neural network."* Without traces, tool timing, token counts, and eval results, the agent is a black box in exactly the place where black boxes are least acceptable.

**Required from day one:**

- Trace per request with stable `trace_id`.
- Spans for each tool (latency, success/failure, error reason).
- Model name and prompt template version.
- Token counts (input, output, cached) and estimated cost.
- Verification outcome (pass / repaired / failed) and unsupported-claim count.
- User feedback (Helpful / Missing data / Incorrect / Too slow / Source unclear).
- Source-ID list for each turn.

**Do not wait until after the demo.** Observability is the only way to turn early mistakes into evals instead of anecdotes.

**Architecture response:** Langfuse from day 1. Hosted Cloud for class submission under case-study BAA assumption; self-hosted for production. The feedback button taxonomy in the UI feeds the eval backlog directly — see [USERS §Feedback Loop](./Claude_Users_v2.md#feedback-loop--how-the-agent-improves).

---

## Prioritized Mitigation Plan

| Priority | Mitigation | Why |
|---|---|---|
| 1 | Patient-scoped read-only gateway with task token | Prevents agent from becoming a privilege escalator |
| 2 | Sidecar holds zero DB credentials | Prevents shadow-EHR failure mode |
| 3 | Source-packet contract | Makes verification and audit possible |
| 4 | Deterministic verifier with active-status rule | Blocks unsupported clinical claims; the most important data-quality safeguard |
| 5 | OpenEMR audit-log extension (agent_turn event) | Reconstructs agent access for compliance |
| 6 | Langfuse tracing | Exposes tool order, latency, cost, failures |
| 7 | Synthetic eval dataset | Tests risks a happy-path demo will not reveal |
| 8 | Short-lived cache (Redis, 5-min) | Improves latency without storing generated clinical prose |
| 9 | Defer unstructured RAG to v2 | Avoids the hardest hallucination + prompt-injection surface in MVP |
| 10 | Deployment runbook (rotate creds, enforce audit globals, secrets management) | Closes the soft-underbelly findings |

---

## Top Findings to Feature in the Defense (Ranked)

If asked "walk me through your most important finding" — this is the order:

1. **Trust model is strong; integrate through it, not around it.** OAuth2 + SMART on FHIR + `AclMain` + `EventAuditLogger` is layered and proven. Agent reads via FHIR. No direct SQL.

2. **Sidecar with no DB credentials is the security architecture's load-bearing decision.** It prevents the agent from becoming a shadow EHR with weaker authorization.

3. **The FHIR scope-only authorization gap.** Real, mitigable, and the audit-driven reason the gateway adds an independent ACL check + short-lived patient-bound task token. Konstantin identified this in the peer defense; my architecture addresses it.

4. **Data quality is the dominant agent-failure mode, not security.** Polymorphic `lists`, dual medication storage, free-text drug names, missing LOINC codes, `patient_data` blanks. Source-packet builder + verifier active-status rule + stale-data labeling + blank-vs-negative discipline are the safeguards.

5. **Audit logging needs an agent-turn extension.** API-level logging is insufficient for a synthesizing agent.

6. **Deployment defaults are the soft underbelly.** Default credentials, audit toggles, encryption keys, `display_errors`. Runbook items, but they belong in the audit.

---

## What I Would Have Missed Without This Audit

- I would have used direct SQL because it's faster to write. The audit showed FHIR is mature and inheriting it is higher leverage.
- I would have given the sidecar DB credentials. The audit showed that creates a shadow EHR.
- I would have trusted the OAuth scope as sufficient authorization. The audit showed it isn't, and the task-token gateway exists because of that finding.
- I would have treated the `lists` table as a clean active-medications source. The audit showed inactive entries hide there; the verifier's active-status rule is now the primary safeguard.
- I would have logged at the API level. The audit showed that's insufficient and the architecture writes turn-level events.
- I would have shipped with note-RAG in v1 because it's technically interesting. The audit showed unstructured free text is the highest hallucination-risk surface.
- I would have treated blank demographic fields as negative facts. The audit showed they aren't, and a dedicated eval case now exists.

---

## Audit Impact on Architecture (Trace)

Every architectural decision in [Claude_Architecture_v2.md](./Claude_Architecture_v2.md) traces back to a finding here:

| Audit Finding | Architecture Response |
|---|---|
| S1 default creds | Deployment runbook; Railway env-var rotation |
| S2 sidecar no DB | Sidecar holds zero DB credentials |
| S3 narrower agent auth | Patient-bound task token + server-supplied `patient_uuid` |
| S5 FHIR scope-only gap | Independent ACL/purpose-of-use check at gateway |
| S6 legacy SQL | Agent calls only `src/` services and FHIR |
| S7 PHI leakage | Metadata-only traces; PHI redaction by default |
| S8 prompt injection | Defer note RAG; treat chart text as data |
| P1 bounded retrieval | Tier-1 / Tier-2 / Tier-3 staging |
| P3 5-table lab join | Lab tool is Tier-2 with loading indicator |
| P4 medication union | `get_active_medications` reconciliation; verifier active-status rule |
| A3 audit-log gap | "agent_turn" event with `trace_id` |
| D1 active vs historical `lists` | Verifier active-status rule |
| D2 free-text drug names | Normalization step in source-packet builder |
| D5 blank ≠ negative | Verifier rejects negative claims without explicit negative source |
| C1 minimum necessary | Narrow `user/<resource>.rs` scopes |
| C5 breach reconstructability | Tool-level + source-ID logging |
| Observability requirement | Langfuse from day 1 + feedback buttons feeding eval backlog |

**Final position:** OpenEMR can support this project, but only if the agent is treated as a controlled clinical data consumer, not an all-access chatbot. The safest useful first version is small: Railway-hosted for speed, OpenEMR-gated for access control, sidecar-orchestrated for AI iteration (no DB credentials), source-packet-based for verification, observable from the first request.
