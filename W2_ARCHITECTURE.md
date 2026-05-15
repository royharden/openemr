# Week 2 Clinical Co-Pilot Architecture

**Multimodal Evidence Agent: document vision, hybrid RAG, supervised routing, and eval-driven quality gates**

Version: 1.0
Owner: Workstream D (Integration, Demo, Docs)

---

## 1. Overview

Week 1 delivered a **read-only clinical assistant** that surfaces verified briefings from structured OpenEMR records. The agent reasons over 6 tools, enforces patient scoping, and gates claims via deterministic verifier rules.

Week 2 extends this with **document understanding, evidence retrieval, and multi-agent orchestration**:

- **Vision:** Extracts structured facts from lab PDFs, intake forms, and medication-list documents using Claude Sonnet 4.6 + pdfplumber bbox anchoring.
- **Hybrid RAG:** Retrieves clinical-guideline evidence (CDC ACIP, openFDA, ADA 2026, ACC/AHA 2026, HMS Library of Evidence) using BM25 + Voyage dense embeddings, fused with Reciprocal Rank Fusion and reranked by Cohere (with a local cross-encoder fallback). Per-chunk context summaries are prepended to the BM25 token stream so a chunk about "influenza vaccination" also retrieves on "flu shot." A clinical-synonym query rewriter and domain-specific source filters run before retrieval.
- **Supervisor:** A LangGraph state machine whose routing is a set of deterministic functions on the graph's conditional edges (no LLM hop). It coordinates intake extraction, evidence retrieval, synthesis, an LLM critic safety gate, and deterministic verification.
- **Eval Gate:** A 141-case golden suite with 12 boolean rubrics. CI blocks PRs on regression; a pre-push hook validates a 10-case smoke; a nightly live-API workflow watches for vendor drift.

**Design principle:** Trustworthy 30% over impressive 80%. Every extracted fact, every evidence citation, every refusal must be inspectable and source-grounded.

---

## 2. Extended Citation Contract

Week 1 packets carried OpenEMR metadata (patient_uuid, source_table, field, observed_at, freshness).

Week 2 extends `SourcePacket` with **document and guideline fields**:

```python
SourcePacket (Pydantic):
  # --- Wk1 fields (unchanged) ---
  source_id: str              # unique per claim
  patient_uuid: str
  resource_type: str          # "Observation", "AllergyIntolerance", ...
  source_table: str           # "procedure_result", "lists", ...
  field: str
  label: str
  value: Any
  unit: str | None
  observed_at: str | None
  freshness: Literal["recent", "stale", "unknown"]
  status: str | None
  sensitive: bool

  # --- Wk2 extensions (all optional, defaults None) ---
  source_type: "openemr_packet" | "document_extract" | "guideline_chunk"
  page_or_section: str        # e.g., "page 2", "vitals section"
  field_or_chunk_id: str      # lab panel name, chunk ID, etc.
  quote_or_value: str         # verbatim text from source
  bbox: (x0, y0, x1, y1)      # normalized [0, 1] rectangle
  bbox_unit: "exact" | "approximate"
  confidence: float           # [0, 1]
  page_index: int
  recommendation_grade: str   # "ACIP-A", "USPSTF-B", etc.
  source_year: int
  source_organization: str    # "CDC-ACIP", "openFDA", etc.
```

**Contract enforcement:**
- Pydantic validates schema shape and bbox/confidence ranges.
- Verifier rules check citation completeness (`citation_present`), bbox well-formedness (`bbox_well_formed`), quote verbatim match (`quote_verbatim_in_pdf`), and chunk corpus membership (`chunk_id_in_corpus`).
- Every rubric is a **boolean deterministic function** — no LLM-as-judge anywhere.

---

## 3. Document Intake & Vision Extraction

### 3.1 Extractors

**`extractors/lab_pdf.py`**
- Input: PDF file (lab report or similar).
- VLM: Claude Sonnet 4.6 vision (Anthropic API, called from the sidecar).
- Output schema: `LabResult` Pydantic model.
  - Fields: test_name, value, unit, reference_range, collection_date, abnormal_flag, status.
  - Each field carries a source packet with deterministic bbox via pdfplumber text-match — the VLM proposes values; pdfplumber confirms each value appears verbatim in the PDF text layer and emits the bbox. If text-match fails, the claim is dropped before synthesis.

**`extractors/intake_form.py`**
- Input: PDF, PNG, or JPEG (handwritten or printed intake form).
- VLM: Claude Sonnet 4.6 for image/PDF extraction.
- Output schema: `IntakeFields` Pydantic model.
  - Fields: demographics (name, DOB, address, phone, MRN), chief_concern, current_medications, allergies, family_history.
  - For image-only inputs (no text layer), bbox is null (allowed by schema); `quote_verbatim_in_pdf` skips for that field.
  - For PDF inputs, text-match applies.

**`extractors/medication_list.py`**
- Input: PDF or image (typed, handwritten, or dirty-scan medication lists).
- VLM: Claude Sonnet 4.6 vision with a forced-tool-use call (`emit_medication_list_entries`). For PDFs with a clean text layer, a text-layer fast path recovers entries via regex before falling back to vision.
- Output schema: list of `MedicationListEntry` Pydantic models — `drug_name`, `dose`, `route`, `frequency`, plus a `SourcePacket` per row.
- One repair pass mirrors the lab/intake retry path.

**PHI handling:** Extraction happens in eval mode with mocked vendors during CI; in production, only synthetic test data and real chart documents touch the sidecar. Filename PHI is redacted at the PHP gateway boundary (and again as a Python defense-in-depth pass) before any logger sees it.

### 3.2 Endpoints

**`POST /v1/extract/lab-pdf`**
Request:
```json
{
  "patient_uuid": "...",
  "document_file": "<multipart-file>",
  "document_sha256": "..."
}
```
Response: `ExtractedDocument` (doc_type="lab_pdf", result=LabResult, packets=[SourcePacket, ...])

**`POST /v1/extract/intake-form`**
Request:
```json
{
  "patient_uuid": "...",
  "document_file": "<multipart-file>",
  "document_sha256": "..."
}
```
Response: `ExtractedDocument` (doc_type="intake_form", result=IntakeFields, packets=[...])

**`POST /v1/extract/medication-list`**
Request:
```json
{
  "patient_uuid": "...",
  "document_file": "<multipart-file>",
  "document_sha256": "..."
}
```
Response: `ExtractedDocument` (doc_type="medication_list", result=list[MedicationListEntry], packets=[...])

**`GET /apis/default/api/copilot/medication-reconciliation`** (PHP gateway)
Diffs the most recent Co-Pilot-extracted medication-list facts for the session-scoped patient against active OpenEMR `prescriptions` rows. Returns rows classified as `confirmed` / `newly_listed` / `possibly_discontinued`.

### 3.3 Storage & Persistence

**PHP-side (`DocumentUploadController`):**
- Receives file upload (size and page-count bounded).
- Computes SHA256, stores raw bytes in OpenEMR's `DocumentService`.
- Calls the sidecar `/v1/extract/{lab-pdf,intake-form,medication-list}`.
- Routes derived facts to their appropriate persistence path (below) and returns extracted facts to the UI.

**Lab values — native OpenEMR writeback (`LabResultWriter`):**
- Lab extractions are written through OpenEMR's native lab chain: `procedure_order` → `procedure_order_code` → `procedure_report` → `procedure_result`, joined to `uuid_registry`.
- Rows are tagged `[copilot-extracted]` in `procedure_order.notes` so they are filterable, auditable, and reversible.
- The writer is transactional: a partial failure rolls back the order, report, and result rows together.
- An environment flag gates production-mode writes; eval-mode runs against fixtures.

**Intake forms — patient creation (`CreatePatientFromIntake`):**
- An extracted intake form can idempotently create a `patient_data` row.
- Idempotency key: `sha256(intake_form_sha256)`. A second upload of the same form does not duplicate the patient.

**Residual facts — `copilot_document_facts`:**
- Anything that doesn't belong in a native table (notes, extracted metadata for medication-list reconciliation, etc.) is persisted here.
- Columns: id, patient_uuid, document_sha256, field_path, extracted_value, extracted_at, idempotency_key (UNIQUE).
- Idempotency key: `sha256(patient_uuid + document_sha256 + field_path)` — one row per extracted field, deduped on re-upload.

---

## 4. Hybrid Retrieval & RAG

### 4.1 Corpus & Indexing

**Sources (Wk2):**
- **CDC ACIP** (public domain, no API key): adult immunization recommendations and schedules.
- **OpenFDA drug labels** (API): 25 high-frequency primary-care drugs (e.g., lisinopril, metformin, atorvastatin).
- **ADA 2026** Standards of Care in Diabetes.
- **ACC/AHA 2026** lipid- and cardiovascular-prevention guidelines.
- **HMS Library of Evidence**.

**Chunking:** Section-aware split that preserves recommendation grades and source metadata.

**Contextual retrieval:** At ingestion time, each chunk is run through a short Haiku 4.5 prompt that produces an ~80-token context summary describing what the chunk is about within its parent document. The summary is stored in a `context_summary` column and prepended to the BM25 token stream for that chunk (the verbatim chunk text is preserved unchanged in `get_chunk`).

**Storage:** `sqlite-vec` (embedded vector database; no external service).
- Table: `chunks` (id, source_id, chunk_text, context_summary, embedding, source_year, grade, source_org, ...).
- Index: sqlite-vec on the embedding vector.
- Current production corpus: **593 chunks** across the five sources.

### 4.2 Retrieval Pipeline

**Query preprocessing.** Before retrieval, the query is run through two passes:

1. **Clinical-synonym query rewriter** expands common abbreviations and clinical synonyms ("HTN" → "hypertension", "DM2" → "type 2 diabetes", etc.).
2. **Domain-specific source filters** classify the query and bias retrieval toward the right corpora — vaccine questions prefer CDC ACIP; dosing questions prefer openFDA labels; lipid/CV questions prefer ACC/AHA; diabetes-care questions prefer ADA.

**HybridRetriever:**

1. **Sparse (BM25):** `rank_bm25` scores chunks by keyword match against the rewritten query (over the contextualized token stream).
2. **Dense (Vector):** Voyage `voyage-4-large` embeddings queried against the sqlite-vec index.
3. **Reciprocal Rank Fusion (RRF):** the two candidate lists are fused by rank — RRF replaces the older max-score-union approach so a chunk that ranks reasonably well in both lists outranks one that only spikes in a single list.
4. **Rerank:** `CohereReranker` (Cohere Rerank 3.5 API) scores the fused top-N against the original query.
   - Fallback: a local cross-encoder if Cohere is unavailable or rate-limited.
5. **Output:** Top-5 reranked chunks as `GuidelineChunk` packets (source_type="guideline_chunk", chunk_id_in_corpus, source_year, recommendation_grade, source_organization).

**Deterministic eval mode:** Voyage and Cohere responses are mocked under `COPILOT_EVAL_MODE=1` so eval runs are offline, fast, and reproducible without vendor rate limits.

---

## 5. LangGraph Supervisor & Multi-Agent State

### 5.1 State Machine

`CopilotState` (TypedDict):
```python
{
    "patient_uuid": str,
    "trace_id": str,
    "use_case": UseCase,  # pre_room_brief | what-changed | ... | free_text_followup

    # Input
    "question": str | None,
    "selected_tools": list[ClinicalToolName],
    "packets": list[SourcePacket],

    # Extraction phase
    "extracted_documents": list[ExtractedDocument],
    "extraction_packets": list[SourcePacket],

    # Retrieval phase
    "retrieved_chunks": list[GuidelineChunk],
    "rag_packets": list[SourcePacket],

    # Synthesis phase
    "llm_output": LLMOutput,

    # Critic phase
    "critic_status": Literal["pending", "accepted", "warned", "rejected"],
    "critic_verdict": CriticVerdict,

    # Verification phase
    "verified_response": VerifiedResponse,
    "verifier_issues": list[VerifierIssue],

    # Metadata
    "supervisor_routing_log": list[dict],
}
```

### 5.2 Supervisor Routing (Deterministic)

The supervisor is **not a graph node** — it is a set of deterministic routing functions wired into LangGraph's conditional edges. With no LLM hop in the router, every routing decision is reproducible, free, and inspectable line-by-line in `state.supervisor_routing_log`. The full sequence:

```
START
  ├── route_from_start:
  │     IF "attach_and_extract" in selected_tools:    → intake_extractor_node
  │     ELSE:                                          → evidence_retriever_node
  │
intake_extractor_node
  └── route_from_intake:                               → evidence_retriever_node
evidence_retriever_node
  └── route_from_retriever:                            → synthesizer_node
synthesizer_node
  └── route_from_synthesizer:                          → critic_node
critic_node
  └── route_from_critic:                               → verifier_node
verifier_node
  └── route_from_verifier:                             → END
```

Every transition is appended to `state.supervisor_routing_log` and emitted as a Langfuse span.

### 5.3 Worker Nodes

**`intake_extractor_node`:**
- Calls `/v1/extract/{lab-pdf,intake-form,medication-list}` for each attached document.
- Populates `state.extracted_documents`, `state.extraction_packets`.

**`evidence_retriever_node`:**
- Takes `state.question` or infers a retrieval query from `state.packets`.
- Calls `HybridRetriever`; populates `state.retrieved_chunks`, `state.rag_packets`.

**`synthesizer_node`:**
- Prompt: `app/prompts/brief_synthesis.txt` + tool results + evidence chunks.
- LLM: Claude Haiku 4.5 (fast synthesis, low cost).
- Calls `ClinicalToolExecutor.plan_tools()` → gateway executes → returns packets.
- Output: `LLMOutput` (claims, missing_data, refusals, followups, usage metrics).

**`critic_node`:**
- Re-reads the synthesizer's output against the supplied evidence and a set of deterministic safety policies (no uncited dose-change suggestions, no clinical action prose without an authoritative source, etc.).
- Emits a `CriticVerdict` with status `accepted`, `warned`, or `rejected`.
- On `rejected`, rewrites `state.llm_output` to a safe refusal before the verifier sees it.
- On `warned`, tags the response with a warning chip; the verifier still runs.
- Live mode uses a Haiku 4.5 forced-tool-use call; eval mode uses the deterministic policy path; the live path falls back to the deterministic policy on any vendor failure.

**`verifier_node`:**
- Runs all boolean rubrics on `LLMOutput` + packets.
- Drops uncited / factually inconsistent / out-of-scope claims.
- Merges `state.critic_verdict` into the dumped `VerifiedResponse`.
- Logs each issue (rule, severity, source_id).
- Output: `VerifiedResponse` (accepted claims, refusals, verifier_status, issues).

---

## 6. Eval Gate & CI Integration

### 6.1 Golden Dataset

**141 cases** in `evals/cases/` subdirectories:
- **Wk1 regression (34 cases):** tool routing, refusals, identity, immunizations — Week 1 behavior preserved.
- **Extraction:** lab panel parsing, intake completeness, image-only forms, dirty scans.
- **RAG:** BM25-only retrieval, vector-only retrieval, fused retrieval, rerank quality.
- **Citation:** bbox accuracy, verbatim quote matching, chunk corpus membership.
- **Refusal:** out-of-scope queries, prompt injection in documents, PHI in query.
- **Integrity:** lab writeback transactional integrity, idempotency, status semantics, env-gated production write.
- **Critic (4 cases):** accept / warn / reject branches.
- **Medication list (5 cases):** happy path, dirty scan, dose ambiguity, reconciliation match / mismatch.
- **Graph end-to-end:** full supervisor → workers → verifier chain.

### 6.2 Rubrics (Boolean, No LLM Judge)

The full rubric set, each a deterministic Python function in `evals/rubrics.py`:

1. **schema_valid** — Response validates against the `VerifiedResponse` schema.
2. **citation_present** — Every accepted claim has ≥ 1 `source_id`.
3. **factually_consistent** — Numbers and ISO dates in claim text appear verbatim in cited packet evidence.
4. **safe_refusal** — Out-of-scope / injection queries produce a refusal when `expectations.must_refuse=true`.
5. **no_phi_in_logs** — Exported traces contain no SSN / phone / MRN patterns.
6. **integrity_writeback_present** — Lab integrity cases must show the writeback row.
7. **integrity_no_dup** — Re-upload of the same document does not duplicate rows.
8. **integrity_status_preliminary** — Co-Pilot-written labs land with the correct preliminary status.
9. **integrity_writeback_gated_off_in_prod** — Production-mode writes require the env-gate flag.
10. **integrity_uses_collection_date** — Lab writeback uses the document's collection date, not "now".
11. **critic_verdict** — Critic produces the expected accept / warn / reject branch for each critic case.
12. **medication_list_reconciled** — Extracted medication list produces the expected confirmed / newly_listed / possibly_discontinued bucket assignment.

**Floor matrix** (`evals/floor.json`):
```json
{
  "schema_valid":                          0.98,
  "citation_present":                      0.98,
  "factually_consistent":                  0.95,
  "safe_refusal":                          1.00,
  "no_phi_in_logs":                        1.00,
  "integrity_writeback_present":           1.00,
  "integrity_no_dup":                      1.00,
  "integrity_status_preliminary":          1.00,
  "integrity_writeback_gated_off_in_prod": 1.00,
  "integrity_uses_collection_date":        1.00,
  "critic_verdict":                        0.95,
  "medication_list_reconciled":            1.00
}
```

If any rubric drops below its floor (or regresses by more than 5%), **CI blocks the PR**.

### 6.3 CI Integration

**Pre-push (local):**
- `.pre-commit-config.yaml` hook runs a 10-case smoke subset.
- Blocks the commit if any smoke case fails.

**GitHub Actions (`.github/workflows/eval-gate.yml`):**
- Runs the full 141-case suite on every PR.
- Posts a pass / fail matrix to the PR comment.
- Exits with code 1 if any floor is violated → PR cannot merge.

**Nightly live smoke** (`.github/workflows/eval-gate-live.yml`):
- Runs a 10-case smoke against the real Anthropic / Voyage / Cohere APIs.
- Alerts on vendor outages and tracks latency / cost drift.

**Regression dry-run evidence:** `agent/copilot-api/evals/regression_dry_run.md` contains the plant-and-revert proof — we planted a bug that short-circuits the `citation_present` rubric, captured the failing gate output, reverted, and captured the matching pass output.

---

## 7. Observability & Cost

### 7.1 Langfuse Integration

**No PHI in traces:**
- `patient_uuid` is hashed at the trace boundary.
- Names, SSNs, and other identifiers are redacted from trace inputs before the SDK sees them.
- Claim text that contains clinical action prose is dropped by the verifier before the trace is closed.
- Log only: trace_id, node name, duration, token usage, tool name, packet counts, rubric outcomes.

**Trace structure:**
```
trace_id: <UUID>
├─ intake_extractor_node     (duration, doc_type, packet_count, confidence_stats)
├─ evidence_retriever_node   (duration, query_text_hash, chunk_count, rerank_score)
├─ synthesizer_node          (duration, tokens, cost, refusal_reason if any)
├─ critic_node               (duration, verdict, branch, fallback_used)
└─ verifier_node             (duration, issues_count, dropped_claims, final_status)
```

Supervisor routing decisions ride alongside each node span as metadata so the routing log is replayable from the trace alone.

**Cost tracking:**
- Per-turn: Sonnet (extraction), Haiku (synthesis + critic), Voyage (embedding), Cohere (rerank).
- Aggregate: p50 / p95 latency, cost per extraction, cost per answer.
- Full Wk2 breakdown and the latency-canary methodology live in [`cost_analysis_Wk2.md`](cost_analysis_Wk2.md). The helper that pulls real Langfuse traces and computes the percentiles is at [`latency_percentiles.py`](latency_percentiles.py).

### 7.2 Startup Validation

`app/startup.py` `validate_provider_credentials()`:
- Checks Anthropic, Voyage, and Cohere API keys with one dummy call per provider.
- Fails fast at container startup if any key is missing or invalid (503 on `/healthz` until the self-test passes).
- Railway / Docker health probes wait for 200 on `/healthz` before marking the container healthy.

---

## 8. File Ownership Zones

| Zone | Owner | Notes |
|---|---|---|
| `app/extractors/` | Vision | Lab PDF, intake form, medication list extractors. |
| `app/rag/` | RAG | Corpus, retriever, reranker, contextualization, query rewriter, source filters, synonyms. |
| `app/graph/` | Orchestration | Supervisor routing functions, worker nodes, critic, state. |
| `app/verifier.py` | Wk1 (extended) | Core verifier rules; Wk2 adds bbox / quote / chunk rules. |
| `app/schemas.py` | Locked | Contract-freeze; `SourcePacket` and extracted-doc schemas. |
| `app/routes.py` | Routes | `/v1/copilot/answer`, `/v1/extract/*`, `/v1/rag/retrieve`. |
| `app/observability.py` | Telemetry | Langfuse wiring; PHI scrub at the boundary. |
| `evals/` | Eval | 141-case suite, rubrics, runner, floor matrix, regression dry-run. |
| `tests/` | Shared | Per-module unit tests; integration tests shared. |
| `.github/workflows/eval-gate.yml` | CI | PR-blocking gate. |
| `interface/modules/custom_modules/oe-module-clinical-copilot/` | PHP | Module: gateway, controllers, services (`LabResultWriter`, `CreatePatientFromIntake`), JS (`copilot.js` with the click-to-source drawer, `lab_trends.js`), CSS, PDF.js vendored assets. |

---

## 9. PHI & Security Hardening

### 9.1 Multi-Layer PHI Scan

Scrubbing runs at four points:

1. **Trace inputs:** Patient name, SSN, DOB, phone, MRN are redacted before payloads cross the sidecar's logging boundary.
2. **LLM responses:** The verifier rule `detect_prose_action_phrases` drops claims with clinical-action instructions that name a patient.
3. **Eval CI logs:** `stderr` / `stdout` are scanned for SSN / phone / MRN patterns before a test is allowed to pass.
4. **Corpus ingestion:** Chunks contain only de-identified guideline text; a copyright-tripwire scan fails the build if a copyrighted phrase is detected.

### 9.2 Filename Redaction

Patient names and other identifiers in upload filenames (e.g. `Margaret Chen lipid panel.pdf`) are redacted to a fixture-key hash at the PHP gateway boundary, with a Python defense-in-depth pass inside the extractor.

### 9.3 Provider Credential Validation

`startup_self_test()`:
- Validates all API keys at sidecar startup.
- Tests: Anthropic (Haiku request), Voyage (dummy embed), Cohere (dummy rerank).
- If any test fails, the sidecar returns 503 on `/healthz` until keys are fixed.

---

## 10. Testing Discipline (5-Layer Pyramid)

| Layer | Trigger | What it covers |
|---|---|---|
| **L1 Unit** | `pytest tests/unit/` | Pydantic schema validation, bbox normalization, retriever components, critic policy, extractor parsers, gateway services. |
| **L2 Integration** | `pytest tests/integration/` | End-to-end extraction via `/v1/extract/*`, hybrid retrieval against the indexed corpus, graph happy-path. |
| **L3 E2E smoke** | pre-push hook | 10-case graph smoke: extract → retrieve → synthesize → critic → verify. |
| **L4 Eval** | `python -m evals.runner --rubric-report` (CI gate) | 141-case golden suite with the 12 boolean rubrics. |
| **L5 Live Smoke** | `.github/workflows/eval-gate-live.yml` (nightly) | Same 10 cases with real APIs; latency and cost metrics. |

**Aggregate today:** 571 pytest tests, 141 eval cases, all 12 rubric floors at 100%.

**Test coverage floors (per module):**
- `app/extractors/`: 90%
- `app/rag/`: 85%
- `app/graph/`: 80%
- `evals/`: N/A (fixture code, not prod).

**PR must-haves:**
- Any code change adds a test (enforced by `check_pr_has_tests.py`).
- Coverage floors cannot be lowered ad hoc.
- Test catalog auto-generated (`tests/CATALOG.md`, validated pre-push).

---

## 11. Reference to Week 1 Architecture

The W2 build is **layered on top of Wk1**, not a replacement. Wk1 components **unchanged**:
- 6-tool read-only gateway (`get_patient_identity`, `get_active_problems`, `get_active_medications`, `get_allergy_list`, `get_recent_labs`, `get_immunization_history`).
- Deterministic verifier (11 rules: patient binding, source attribution, stale-data caveat, etc.).
- Langfuse observability (trace_id joined to `agent_turn` audit row).
- Clinician feedback loop (Helpful / Incorrect / Too slow / Source unclear / Missing data).

**Wk2 extends:**
- `SourcePacket` schema (adds citation fields).
- Verifier rule set (adds bbox / quote / chunk rules).
- Tool set (adds `attach_and_extract` for document vision).
- LLM call stack (adds Voyage embedding, Cohere rerank, Sonnet vision, Haiku critic).
- UI: click-to-source preview drawer (vendored PDF.js with Subresource Integrity), Lab Trends widget.

**Full brief workflow (Wk2):**
1. Clinician attaches a document (lab PDF, intake form, or medication list).
2. The graph routes through intake-extractor → evidence-retriever → synthesizer → critic → verifier.
3. The verifier emits the `VerifiedResponse` with citation chips.
4. Clicking a citation chip opens the preview drawer at the cited page with the bbox highlighted.
5. The Lab Trends widget appears below the Co-Pilot card when Co-Pilot-extracted results exist for the patient.

---

## 12. Key Decisions & Tradeoffs

| Decision | Rationale |
|---|---|
| Sonnet 4.6 vision (not 4.5) | 4.6 has better document understanding; cost trade acceptable for extraction accuracy. |
| Haiku 4.5 for synthesis and critic | Haiku is sufficient given the verifier gate and evidence constraints; ~10× cheaper than Sonnet. |
| Supervisor as edge-routing functions (not a node, not an LLM) | Avoids token overhead, makes routing auditable, eliminates hallucinated tool calls. |
| pdfplumber bbox (not VLM-emitted) | VLM bbox is often inaccurate; text-match via pdfplumber is deterministic. |
| Boolean rubrics (no LLM judge) | LLM judges are slow, expensive, and unreliable. Deterministic rubrics are fast and reproducible. |
| CDC ACIP (not USPSTF) | ACIP is public-domain and primary-care-aligned; USPSTF API access has a multi-week lead time. |
| Eval mode with mocked vendors | The full suite runs offline, fast, reproducible; real APIs are exercised in nightly smoke only. |
| sqlite-vec (not Pinecone / Weaviate) | Embedded, no SaaS cost, portable, good enough for the corpus size. |
| Cohere Rerank with local fallback | Rerank improves retrieval quality; the local fallback keeps CI independent of vendor uptime. |
| Reciprocal Rank Fusion (not max-score union) | A chunk that ranks well in both BM25 and vector outranks one that only spikes in a single list. |
| Anthropic contextual retrieval | Per-chunk summary prepended to BM25 stream improves cross-vocabulary recall ("flu shot" → "influenza vaccination"). |
| Critic agent as a worker, not a verifier rule | The critic is allowed to rewrite to a safe refusal; the verifier is allowed only to drop claims. Separating them keeps each layer's responsibility narrow. |
| Native lab writeback (not custom table only) | Co-Pilot-extracted labs land in the same `procedure_*` tables a human-entered lab would, so the downstream chart, FHIR layer, and audit log all "just work." |
| Vendored PDF.js with SRI | No third-party CDN dependency for the click-to-source drawer; integrity-pinned. |

---

## 13. Known Limitations & Future Work

- **FHIR `Observation` write deferred.** Lab values land in OpenEMR's native `procedure_*` chain (which FHIR exposes through the existing surface), but a direct `FHIR Observation` resource POST is future work.
- **USPSTF corpus deferred.** Wk2 ships ACIP / openFDA / ADA / ACC/AHA / HMS-LoE; USPSTF will be added in a later sprint.
- **Multi-document context.** The supervisor routes one document at a time; multi-document synthesis (comparing two lab PDFs in the same turn) is future work.
- **Streaming responses.** Wk2 uses request-response; streaming token generation is future.

---

## 14. Verification Checklist

- [x] Extractors shipped: `lab_pdf.py`, `intake_form.py`, `medication_list.py`.
- [x] Hybrid RAG shipped with RRF fusion, Cohere rerank + local fallback, Anthropic contextual retrieval, clinical-synonym query rewriter, and domain-specific source filters.
- [x] LangGraph with deterministic edge routing and five worker nodes (intake / retriever / synthesizer / critic / verifier).
- [x] Citation contract extended (`SourcePacket` with bbox / quote / chunk-id fields).
- [x] Eval-driven CI gate active (`.github/workflows/eval-gate.yml` — 141 cases, 12 rubric floors).
- [x] Pre-push 10-case smoke blocks commits (`.pre-commit-config.yaml`).
- [x] Nightly live-smoke workflow active (`.github/workflows/eval-gate-live.yml`).
- [x] Deterministic eval mode (mocked vendors for offline runs).
- [x] PHI multi-layer scan (traces, responses, logs, corpus, filenames).
- [x] Provider credentials validated at sidecar startup.
- [x] Regression dry-run committed (`agent/copilot-api/evals/regression_dry_run.md`).
- [x] Click-to-source preview drawer (vendored PDF.js + SRI).
- [x] Lab Trends widget.
- [x] Medication-list reconciliation endpoint.
- [x] Native lab writeback to `procedure_*` chain with `[copilot-extracted]` provenance tag.

---

**End of W2 Architecture Document**
