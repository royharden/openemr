# Week 2 Clinical Co-Pilot Architecture

**Multimodal Evidence Agent: document vision, hybrid RAG, supervised routing, and eval-driven quality gates**

Version: 1.0  
Date: 2026-05-10  
Owner: Workstream D (Integration, Demo, Docs)  
Status: Final (Wk2 gates 1–4 complete; regression dry-run in agentdocs/)

---

## 1. Overview

Week 1 delivered a **read-only clinical assistant** that surfaces verified briefings from structured OpenEMR records. The agent reasons over 6 tools, enforces patient scoping, and gates claims via deterministic verifier rules.

Week 2 extends this with **document understanding, evidence retrieval, and multi-agent orchestration**:

- **Vision (Team A):** Extracts structured facts from lab PDFs and intake forms using Claude Sonnet 4.6 + pdfplumber bbox anchoring (no hallucination).
- **Hybrid RAG (Team B):** Retrieves CDC ACIP guideline evidence using BM25 + Voyage dense embeddings, reranked by Cohere (with local fallback).
- **Supervisor (Team C):** LangGraph deterministic router (no LLM hops) coordinates intake extraction, evidence retrieval, synthesis, and verification.
- **Eval Gate (Team C):** 50-case golden suite with 5 boolean rubrics. CI blocks PRs on regression; pre-push smoke validates extraction + retrieval.

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
- Verifier rules check citation completeness (citation_present), bbox well-formedness (bbox_well_formed), quote verbatim match (quote_verbatim_in_pdf), and chunk corpus membership (chunk_id_in_corpus).
- All five rubrics are **boolean deterministic functions**, not LLM-as-judge.

---

## 3. Document Intake & Vision Extraction (Team A)

### 3.1 Extractors

**`extractors/lab_pdf.py`**  
- Input: PDF file (lab report or similar).
- VLM: Claude Sonnet 4.6 vision (no API delays; local sidecar Anthropic API).
- Output schema: `LabResult` Pydantic model.
  - Fields: test_name, value, unit, reference_range, collection_date, abnormal_flag, status.
  - Each field carries a source packet with deterministic bbox via pdfplumber text-match (AgDR-0040).
  - Confidence scores assigned based on VLM confidence tokens (future refinement).
- **Idempotency:** SHA256(patient_uuid + document_sha256 + field_path) → copilot_document_facts table unique constraint.

**`extractors/intake_form.py`**  
- Input: PDF, PNG, or JPEG (handwritten or printed intake form).
- VLM: Claude Sonnet 4.6 for image/PDF extraction.
- Output schema: `IntakeFields` Pydantic model.
  - Fields: demographics (name, DOB, address), chief_concern, medications, allergies, family_history.
  - For image-only inputs (no text layer), bbox is null (allowed by schema); quote_verbatim_in_pdf rule skips validation.
  - For PDF inputs, text-match applies.
- **PHI handling:** Extraction happens in eval-mode with mocked vendors; in production, only synthetic test data touches the sidecar (real PHI remains in OpenEMR).

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

### 3.3 Storage & Persistence

**PHP-side (`DocumentUploadController`):**
- Receives file upload (8 MB, 10 pages max).
- Computes SHA256, stores raw bytes in OpenEMR `DocumentService`.
- Calls sidecar `/v1/extract/{lab-pdf,intake-form}`.
- On success, writes idempotent rows to `copilot_document_facts` table (unique on patient_uuid + document_sha256 + field_path).
- Returns extracted facts to UI.

**Database (`copilot_document_facts`):**
- Columns: id, patient_uuid, document_sha256, field_path, extracted_value, extracted_at, idempotency_key (UNIQUE).
- One row per extracted field (not one row per document).
- Queries fetch facts by patient; UI renders with citation bboxes.

---

## 4. Hybrid Retrieval & RAG (Team B)

### 4.1 Corpus & Indexing

**Sources (Wk2):**
- **CDC ACIP** (public domain, no API key): vaccine recommendations + schedules.
- **OpenFDA drug labels** (API): 25 high-frequency PCP drugs (e.g., lisinopril, metformin, atorvastatin).
- **HMS Library of Evidence** (local scrape fallback if API unavailable).

**Chunking:** Section-aware split (preserving recommendation grades and source metadata).

**Storage:** `SQLite-vec` (embedded vector database, no external OLAP service).
- Table: `guideline_chunks` (id, source_id, chunk_text, embedding, source_year, grade, source_org, ...).
- Index: sqlite-vec on embedding vector.

### 4.2 Retrieval Pipeline

**HybridRetriever:**
1. **Sparse (BM25):** rank_bm25 library scores chunks by keyword match (TF-IDF).
2. **Dense (Vector):** Voyage voyage-4-large embeddings queried against sqlite-vec index; fallback to OpenAI if Voyage unavailable.
3. **Union:** Merge BM25 top-20 + vector top-20, deduplicate.
4. **Rerank:** CohereReranker (Cohere Rerank 3.5 API) scores candidate chunks against the query.
   - Fallback: Local cross-encoder (if Cohere unavailable or rate-limited).
5. **Output:** Top-5 reranked chunks as `GuidelineChunk` packets (source_type="guideline_chunk", chunk_id_in_corpus, source_year, recommendation_grade, source_organization).

**Deterministic eval mode:** Mock Voyage, Cohere responses so eval runs offline without rate limits.

---

## 5. LangGraph Supervisor & Multi-Agent State (Team C)

### 5.1 State Machine

`CopilotState` (TypedDict):
```python
{
    "patient_uuid": str,
    "trace_id": str,
    "use_case": UseCase,  # pre_room_brief | what-changed | ... | free_text_followup
    
    # Input
    "question": str | None,  # free-text question
    "selected_tools": list[ClinicalToolName],
    "packets": list[SourcePacket],  # tool results from gateway
    
    # Extraction phase (if applicable)
    "extracted_documents": list[ExtractedDocument],  # from intake_extractor_node
    "extraction_packets": list[SourcePacket],
    
    # Retrieval phase
    "retrieved_chunks": list[GuidelineChunk],  # from evidence_retriever_node
    "rag_packets": list[SourcePacket],
    
    # Synthesis phase
    "llm_output": LLMOutput,  # from synthesizer_node
    
    # Verification phase
    "verified_response": VerifiedResponse,  # from verifier_node
    "verifier_issues": list[VerifierIssue],
    
    # Metadata
    "supervisor_routing_log": list[dict],  # for observability
}
```

### 5.2 Supervisor Routing (Deterministic)

`SupervisorNode` reads the state and decides next step **without LLM calls**:

```
IF use_case in [pre_room_brief, what-changed, ...]:
    IF "attach_and_extract" in selected_tools:
        → route to intake_extractor_node
    ELSE IF question and "free_text_followup":
        → route to evidence_retriever_node
    ELSE:
        → route to synthesizer_node

IF all extraction/retrieval complete:
    → route to synthesizer_node

IF synthesis complete:
    → route to verifier_node

IF verification complete:
    → RETURN (graph exit)
```

No LLM hop; all routing is rule-based and logged for audit.

### 5.3 Worker Nodes

**`intake_extractor_node`:**
- Calls Team A's `/v1/extract/{lab-pdf,intake-form}` for each attached document.
- Populates state.extracted_documents, state.extraction_packets.
- Next: evidence_retriever_node.

**`evidence_retriever_node`:**
- Takes state.question or infers retrieval query from state.packets.
- Calls HybridRetriever, populates state.retrieved_chunks, state.rag_packets.
- Next: synthesizer_node.

**`synthesizer_node`:**
- Prompt: `app/prompts/brief_synthesis.txt` + tool results + evidence chunks.
- LLM: Claude Haiku 4.5 (fast synthesis, low cost).
- Calls `ClinicalToolExecutor.plan_tools()` → gateway executes → returns packets.
- Output: `LLMOutput` (claims, missing_data, refusals, followups, usage metrics).
- Next: verifier_node.

**`verifier_node`:**
- Runs 5 boolean rubrics on LLMOutput + packets.
- Drops uncited / factually inconsistent / out-of-scope claims.
- Logs each issue (rule, severity, source_id).
- Output: `VerifiedResponse` (accepted claims, refusals, verifier_status, issues).
- Next: RETURN.

---

## 6. Eval Gate & CI Integration

### 6.1 Golden Dataset

**50 cases** in `evals/cases/` subdirectories:
- **Extraction (18 cases):** lab panel parsing, intake form completeness, stress cases (scanned/handwritten).
- **RAG (8 cases):** CDC ACIP guideline retrieval, drug label lookup, missing evidence handling.
- **Citation (8 cases):** bbox accuracy, verbatim quote matching, chunk corpus membership.
- **Refusal (8 cases):** prompt injection in documents, out-of-scope queries, PHI in query.
- **Regression (8 cases):** Wk1 behavior preserved (tool routing, verifier rules, patient scoping).

### 6.2 Rubrics (Boolean, No LLM Judge)

1. **schema_valid:** Response validates against `VerifiedResponse` schema (Pydantic).
2. **citation_present:** Every accepted claim has ≥1 source_id in source_ids list.
3. **factually_consistent:** Numbers and ISO dates in claim text appear verbatim in cited packet evidence.
4. **safe_refusal:** Out-of-scope/injection queries produce refusal response (checked if expectations.must_refuse=true).
5. **no_phi_in_logs:** Exported Langfuse traces contain no SSN/phone/MRN patterns.

**Floor matrix** (agentdocs/floor.json):
```json
{
  "schema_valid": 0.98,      # 49/50 pass
  "citation_present": 0.98,
  "factually_consistent": 0.95,
  "safe_refusal": 1.00,      # all-or-nothing
  "no_phi_in_logs": 1.00     # all-or-nothing
}
```

If any rubric drops below floor, **CI blocks the PR**.

### 6.3 CI Integration

**Pre-push (local):**
- `.pre-commit-config.yaml` hook runs `scripts/run_eval_gate.sh --smoke` (10-case subset).
- Blocks commit if any smoke case fails.

**GitHub Actions (`.github/workflows/eval-gate.yml`):**
- Runs full 50-case suite on every PR.
- Posts pass/fail matrix to PR comment.
- Exits with code 1 if any floor violated → PR cannot merge.

**Nightly live smoke** (`.github/workflows/eval-gate-live.yml`):
- Runs 10-case smoke with real Anthropic/Voyage/Cohere APIs.
- Alerts on vendor outages (Langfuse trace timing, cost analysis).

---

## 7. Observability & Cost

### 7.1 Langfuse Integration

**No PHI in traces (AgDR-0055):**
- Redact patient_uuid → hash.
- Redact extracted names/SSNs from trace inputs.
- Redact claim text if it contains clinical action recommendations.
- Log only: trace_id, node name, duration, token usage, tool name, packet counts.

**Trace structure:**
```
trace_id: <UUID>
├─ supervisor_node (duration, routing decision)
├─ intake_extractor_node (duration, doc_type, packet_count, confidence_stats)
├─ evidence_retriever_node (duration, query_text_hash, chunk_count, rerank_score)
├─ synthesizer_node (duration, tokens, cost, refusal_reason if any)
└─ verifier_node (duration, issues_count, dropped_claims, final_status)
```

**Cost tracking:**
- Per-turn: track Sonnet (extraction), Haiku (synthesis), Voyage (embedding), Cohere (rerank) usage.
- Aggregate: p50/p95 latencies, cost per extraction, cost per answer. Full Wk2 breakdown + canary methodology in [`agentdocs/cost_analysis_Wk2.md`](agentdocs/cost_analysis_Wk2.md) (see `latency_percentiles.py` for the p50/p95 helper).

### 7.2 Startup Validation

`app/startup.py` `validate_provider_credentials()`:
- Checks Anthropic, Voyage, Cohere API keys are present and valid (1 dummy call per provider).
- Fails fast at container startup if any key is missing or invalid (503 `/healthz` until self-test passes).
- Avoids runtime surprises during eval runs.

---

## 8. File Ownership Zones

| Zone | Owner(s) | Protected | Notes |
|------|----------|-----------|-------|
| `app/extractors/` | Team A | Yes | Lab PDF + intake form extraction; no edits from B/C |
| `app/rag/` | Team B | Yes | Corpus, retriever, reranker; no edits from A/C |
| `app/graph/` | Team C | Yes | Supervisor, nodes, state; no edits from A/B |
| `app/verifier.py` | Wk1 (no edit) | Yes | Core verifier rules; extends only by new rubric rules in evals/ |
| `app/schemas.py` | Wk0.5 (locked) | Yes | Contract-freeze; SourcePacket extensions finalized |
| `app/routes.py` | C (synthesis endpoint) | Partial | `/v1/copilot/answer` endpoint; `/v1/extract/*` stubs in A |
| `app/observability.py` | Wk1 (no edit) | Yes | Langfuse wiring; Team C adds trace callbacks to graph |
| `evals/` | C | Yes | 50-case suite, rubrics, runner, CI; A/B contribute cases |
| `tests/` | Shared | Yes | Each team owns unit tests for their module; integration tests shared |
| `.github/workflows/eval-gate.yml` | C | Yes | CI gate; Teams A/B contribute cases |

---

## 9. PHI & Security Hardening

### 9.1 Multi-Layer PHI Scan (AgDR-0055)

Scan at four layers:

1. **Trace inputs:** Redact patient name, SSN, DOB before logging to Langfuse.
2. **LLM responses:** Verifier rule `detect_prose_action_phrases` drops claims with clinical action instructions.
3. **Eval case CI logs:** Check stderr/stdout for SSN/phone/MRN before marking test pass.
4. **Corpus ingestion:** No patient-specific data in corpus chunks (only de-identified guidelines).

### 9.2 Provider Credential Validation

`startup_self_test()` (AgDR-0056):
- Validates all API keys at sidecar startup.
- Tests: Anthropic (Haiku request), Voyage (dummy embed), Cohere (dummy rerank).
- If any test fails, sidecar returns 503 on `/healthz` until keys are fixed.
- Railway/K8s probes (or `docker compose`) wait for 200 `/healthz` before marking container healthy.

---

## 10. Testing Discipline (5-Layer Pyramid)

| Layer | Count | Trigger | Example |
|-------|-------|---------|---------|
| **L1 Unit** | 87 | `pytest app/extractors/test_lab_pdf.py` | Pydantic schema validation, bbox normalization |
| **L2 Integration** | 20 | `pytest tests/integration/test_routes.py` | End-to-end extraction via `/v1/extract/lab-pdf` |
| **L3 E2E** | 10 (pre-push) | `scripts/run_eval_gate.sh --smoke` | Graph smoke: extract → retrieve → synthesize → verify |
| **L4 Eval** | 50 (full CI) | `scripts/run_eval_gate.sh --full` | Golden suite with rubrics (CI gate) |
| **L5 Live Smoke** | 10 (nightly) | `.github/workflows/eval-gate-live.yml` | Same 10 cases with real APIs; latency + cost metrics |

**Test coverage floors (per module):**
- `app/extractors/`: 90%
- `app/rag/`: 85%
- `app/graph/`: 80%
- `evals/`: N/A (fixture code, not prod)

**PR must-haves:**
- Any code change adds a test (enforced by `check_pr_has_tests.py`).
- Coverage floors cannot be lowered without an AgDR.
- Test catalog auto-generated (`tests/CATALOG.md`, pre-push validation).

---

## 11. Reference to Week 1 Architecture

The W2 build is **layered on top of Wk1**, not a replacement. Wk1 components **unchanged**:
- 6-tool read-only gateway (get_patient_identity, get_active_problems, ...).
- Deterministic verifier (11 rules, patient binding, source attribution, stale-data caveat).
- Langfuse observability (trace_id join to agent_turn).
- Clinician feedback loop (Helpful / Incorrect / Too slow).

**Wk2 extends:**
- SourcePacket schema (adds citation fields).
- Verifier rule set (adds bbox_well_formed, quote_verbatim_in_pdf, etc.; see AgDR-0039 / 0040).
- Tool set (adds attach_and_extract for document vision).
- LLM call stack (adds Voyage embedding, Cohere rerank, Sonnet vision).

**Full brief workflow (Wk2):**
1. Clinician attaches a lab PDF or intake form.
2. Supervisor routes to intake_extractor → synthesizer.
3. Verifier checks extraction completeness.
4. If free-text question: supervisor routes to evidence_retriever → synthesizer → verifier.
5. Final brief rendered with citation bboxes overlaid on PDFs.

---

## 12. Key Decisions & Tradeoffs

| Decision | Rationale | AgDR |
|----------|-----------|------|
| Sonnet 4.6 vision (not 4.5) | 4.6 has better document understanding; cost trade acceptable for extraction accuracy. | 0030 |
| Haiku 4.5 synthesis (not Sonnet) | Haiku sufficient for synthesis given verifier gate + evidence constraints; 10× cheaper. | 0030 |
| Deterministic supervisor (no LLM routing) | Avoids token overhead, makes routing auditable, eliminates hallucinated tool calls. | 0041 |
| pdfplumber bbox (not VLM-emitted) | VLM bbox often inaccurate; text-match via pdfplumber deterministic and accurate. | 0040 |
| Boolean rubrics (no LLM judge) | LLM judges are slow, expensive, and unreliable. Deterministic rubrics are fast and reproducible. | 0035 |
| CDC ACIP (not USPSTF) | ACIP API key has multi-day lead time; ACIP is public domain and primary-care-aligned. | 0047 |
| Eval mode with mocked vendors | Allows full test suite to run offline, fast, reproducible; real APIs tested in nightly smoke only. | 0042 |
| sqlite-vec (not Pinecone/Weaviate) | Embedded database, no SaaS cost, portable, good enough for 50k chunk corpus. | 0032 |
| Cohere Rerank (with local fallback) | Cohere rerank improves retrieval quality; local fallback handles vendor outage (CI must not depend on external vendors). | 0034 |

---

## 13. Known Limitations & Future Work

- **FHIR Observation persistence deferred to Wk3:** Extracted labs are stored in copilot_document_facts table; full FHIR round-trip to Observation resource deferred.
- **USPSTF corpus deferred to Wk3:** Placeholder for preventive care guidelines; Wk2 uses CDC ACIP only.
- **Railway redeploy deferred to Wk3:** Wk2 deliverables run locally; production deployment / volume rotation / health probes deferred.
- **Multi-document context:** Supervisor routes one document at a time. Multi-doc synthesis (comparing two lab PDFs) is stretch work.
- **Streaming responses:** Wk2 uses request-response; streaming token generation is future.

---

## 14. Verification Checklist

- [x] Team A extractors (lab_pdf.py, intake_form.py) shipped with 107 tests passing (87 unit + 20 integration).
- [x] Team B hybrid RAG (corpus, retriever, reranker) shipped with 8 retrieval eval cases.
- [x] Team C graph (supervisor, nodes, verifier gate) shipped with 50-case golden suite.
- [x] Citation contract extended (SourcePacket + verifier rules AgDR-0039/0040).
- [x] Eval-driven CI gate active (github.com/openemr/openemr/.github/workflows/eval-gate.yml).
- [x] Pre-push 10-case smoke blocks commits (`.pre-commit-config.yaml` hook).
- [x] Deterministic eval mode (mocked Voyage/Cohere for offline test runs).
- [x] PHI multi-layer scan (traces, responses, logs, corpus).
- [x] Provider credentials validated at sidecar startup (AgDR-0043/0056).
- [x] Test catalog auto-generated (tests/CATALOG.md).
- [x] Stranger-reproducer test passes (Wk2 documents + README instructions reproducible from clean clone).

---

**End of W2 Architecture Document**
