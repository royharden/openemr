> **Week2-AgentForge Fork:**
>
> The Week 1 read-only Co-Pilot is now a **Multimodal Evidence
> Agent**: it now sees clinical documents (lab PDFs, intake forms, medication
> lists), retrieves matching guideline evidence, routes work through a
> LangGraph supervisor, and gates every PR with a 50+ case eval suite that
> blocks regressions before they reach the demo. A separate Surprise
> deliverable demo shows how we can replace the legacy PHP patient dashboard with a modern React 19 + TypeScript SPA that talks to OpenEMR's FHIR R4 API via
> SMART-on-FHIR.
>
>**Deployed app:** https://openemr-production-f057.up.railway.app
> (admin / pass). Both the legacy OpenEMR dashboard and the Co-Pilot card
> are reachable from the patient summary.
>
>---
>
>### Week 2 deliverables map (PRD → repo)
>
>#### Multimodal Evidence Agent — Main Track
>
>**1. Document ingestion and extraction.** A single tool —
> `attach_and_extract(patient_id, file, doc_type)` — supports three
> document types: `lab_pdf`, `intake_form`, and `medication_list` (a
> third doc type added per the Extension list). Each upload:
>
>- Stores the **raw source document** via OpenEMR's `DocumentService`
>   (no shadow copy of the bytes — the binary lives in OpenEMR's
>   native document store).
> - Returns **strict-schema JSON** validated by Pydantic, with one
>   citation packet per extracted field (page, bounding box, verbatim
>   quote, confidence).
> - **Persists derived facts** to OpenEMR records. Lab values are
>   written through the native `procedure_order` → `procedure_report`
>   → `procedure_result` chain (a transactionally-integrated lab
>   writeback) tagged with a `[copilot-extracted]` provenance marker
>   so they can be filtered, audited, or rolled back. Intake-form
>   extractions can create a new patient row idempotently. Document
>   facts that don't belong in the native tables go to a dedicated
>   `copilot_document_facts` table, idempotency-keyed on
>   `sha256(patient_uuid + document_sha256 + field_path)` so the same
>   document re-uploaded does not duplicate rows.
>
>Code:
> - Extractors: [`agent/copilot-api/app/extractors/lab_pdf.py`](agent/copilot-api/app/extractors/lab_pdf.py),
>   [`intake_form.py`](agent/copilot-api/app/extractors/intake_form.py),
>   [`medication_list.py`](agent/copilot-api/app/extractors/medication_list.py).
> - PHP upload + writeback:
>   [`interface/modules/custom_modules/oe-module-clinical-copilot/src/Controller/DocumentUploadController.php`](interface/modules/custom_modules/oe-module-clinical-copilot/src/Controller/DocumentUploadController.php),
>   the `LabResultWriter` and `CreatePatientFromIntake` services in the
>   same module's `src/` directory.
> - Endpoints: `POST /v1/extract/lab-pdf`,
>   `POST /v1/extract/intake-form`,
>   `POST /v1/extract/medication-list` (sidecar);
>   `POST /apis/default/api/copilot/upload`,
>   `GET  /apis/default/api/copilot/medication-reconciliation` (gateway).
>
>**2. Structured schemas.** All extracted output is validated against
> strict Pydantic schemas in
> [`agent/copilot-api/app/schemas.py`](agent/copilot-api/app/schemas.py)
> before it ever leaves the extractor:
>
>- **`LabResult`** — `test_name`, `value`, `unit`, `reference_range`,
>   `collection_date`, `abnormal_flag`, `status`, plus a `SourcePacket`
>   citation per field.
> - **`IntakeFields`** — `demographics` (name, DOB, sex, address,
>   phone, MRN), `chief_concern`, `current_medications`, `allergies`,
>   `family_history`, plus a `SourcePacket` per field.
> - **`MedicationListEntry`** — one row per medication, with
>   `drug_name`, `dose`, `route`, `frequency`, and citation.
>
>Schema-validation tests in
> [`agent/copilot-api/tests/unit/`](agent/copilot-api/tests/unit/) cover
> every required field, bbox normalization, and the rejection paths
> when a VLM tries to emit a value with no source.
>
>**3. Hybrid RAG + rerank.** The clinical-guideline corpus is built by
> [`agent/copilot-api/scripts/build_corpus.py`](agent/copilot-api/scripts/build_corpus.py)
> from five primary-care-aligned sources: CDC ACIP adult immunization
> recommendations, openFDA drug labels (25 high-frequency PCP drugs),
> ADA 2026, ACC/AHA 2026, and the Harvard HMS Library of Evidence.
> The corpus indexes 593 chunks in an embedded sqlite-vec database
> (no SaaS dependency).
>
>Retrieval pipeline:
>
>1. **Sparse BM25** scores chunks on keyword match (`rank_bm25`).
> 2. **Dense vector** retrieval uses Voyage `voyage-4-large`
>    embeddings against the sqlite-vec index.
> 3. The two candidate lists are **fused with Reciprocal Rank Fusion**.
> 4. **Cohere Rerank 3.5** scores the fused candidates against the
>    query; a local cross-encoder fallback runs if Cohere is
>    unavailable so CI never depends on a third-party vendor.
> 5. **Anthropic contextual retrieval** is applied at ingestion time —
>    every chunk carries a short LLM-generated context summary that is
>    prepended to its BM25 token stream, so a chunk about
>    "influenza vaccination" in an ACIP table also retrieves on
>    "flu shot."
> 6. A **clinical synonym query rewriter** and **domain-specific
>    source filters** restrict retrieval to the right corpora per
>    query class (e.g., vaccine questions prefer ACIP, dosing questions
>    prefer openFDA labels).
>
>Only the top-5 reranked chunks are passed to the answer model.
>
>Code: [`agent/copilot-api/app/rag/`](agent/copilot-api/app/rag/) —
> `corpus.py`, `retriever.py`, `reranker.py`, `embedder.py`,
> `contextualization.py`, `query_rewriter.py`, `synonyms.py`,
> `ingestion/`.
>
>**4. Supervisor + workers.** The agent runs as a LangGraph state
> machine. **The supervisor is implemented as deterministic routing
> functions on the graph's conditional edges, not as a node** — this
> is intentional. With no LLM hop in the router, every routing decision
> is reproducible, free, and inspectable line-by-line in
> `state.supervisor_routing_log`. The two required worker nodes —
> `intake_extractor_node` and `evidence_retriever_node` — are joined by
> `synthesizer_node` (Haiku 4.5 brief generation) and `verifier_node`
> (the boolean rubric gate). A `critic_node` ships as the Extension
> safety LLM that can reject uncited or unsafe claims before they reach
> the verifier.
>
>Code:
> [`agent/copilot-api/app/graph/`](agent/copilot-api/app/graph/) —
> `build.py` (graph wiring), `nodes.py` (worker implementations),
> `supervisor.py` (routing functions), `critic.py`, `state.py`.
>
>The graph:
>
>```mermaid
> flowchart TD
>     START([Question + patient context]) --> SUP{Supervisor<br/>deterministic router}
>     SUP -- "needs_extraction" --> IE["intake_extractor_node<br/>(also services lab_pdf<br/>and medication_list)"]
>     SUP -- "needs_evidence" --> ER[evidence_retriever_node]
>     SUP -- "ready_to_answer" --> SYN[synthesizer_node]
>     IE --> SUP
>     ER --> SUP
>     SYN --> CRIT[critic_node<br/>LLM safety gate]
>     CRIT -- "accept / warn" --> VER[verifier_node]
>     CRIT -- "reject<br/>(rewrites llm_output<br/>to safe refusal)" --> VER
>     VER -- "passes rubric" --> DONE([Answer with citation chips])
>     VER -- "fails rubric" --> SAFE([Safe refusal<br/>no PHI leaked])
>
>    classDef sup fill:#fff3e0,stroke:#e65100,color:#000
>     classDef worker fill:#e3f2fd,stroke:#0d47a1,color:#000
>     classDef critic fill:#f3e5f5,stroke:#4a148c,color:#000
>     classDef terminal fill:#e8f5e9,stroke:#1b5e20,color:#000
>     classDef refusal fill:#ffebee,stroke:#b71c1c,color:#000
>     class SUP sup
>     class IE,ER,SYN,VER worker
>     class CRIT critic
>     class DONE terminal
>     class SAFE refusal
> ```
>
>A rendered PNG of the same diagram is also at
> [`docs/assets/wk2_supervisor_graph.png`](docs/assets/wk2_supervisor_graph.png)
> for environments that don't render Mermaid.
>
>**5. Citation contract.** Every clinical claim in the final response
> carries machine-readable citation metadata. The Week 1 `SourcePacket`
> was extended for Week 2 to add document and guideline-chunk fields,
> giving a single citation shape that works for OpenEMR records,
> document extractions, and guideline chunks:
>
>```python
> SourcePacket:
>     source_id: str
>     source_type: "openemr_packet" | "document_extract" | "guideline_chunk"
>     page_or_section: str               # e.g. "page 2", "vitals section"
>     field_or_chunk_id: str             # lab panel name / chunk id
>     quote_or_value: str                # verbatim from source
>     bbox: (x0, y0, x1, y1) | None      # normalized [0, 1] rectangle
>     bbox_unit: "exact" | "approximate"
>     confidence: float                  # [0, 1]
>     page_index: int
>     recommendation_grade: str          # "ACIP-A", "USPSTF-B", etc.
>     source_year: int
>     source_organization: str           # "CDC-ACIP", "openFDA", etc.
> ```
>
>Bounding boxes for PDF extractions are **deterministic**: the VLM
> proposes values, then `pdfplumber` text-matches each value in the
> PDF's text layer and emits the bbox itself. If a value does not
> appear verbatim in the text layer, the claim is dropped before
> synthesis ever sees it. For image-only inputs (handwritten intake
> forms), bbox is permitted to be null and the verifier skips the
> verbatim-match rule for that field.
>
>The UI side of the contract is a **visual PDF bounding-box overlay**:
> clicking a source chip on any cited claim opens a click-to-source
> preview drawer that loads the original PDF via a vendored copy of
> PDF.js (Subresource Integrity-pinned at
> [`interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/vendor/pdfjs/`](interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/vendor/pdfjs/))
> and draws the saved bbox on the page the citation came from.
>
>Schemas, the citation type, and the verifier rules that enforce
> the contract (`citation_present`, `bbox_well_formed`,
> `quote_verbatim_in_pdf`, `chunk_id_in_corpus`) are at
> [`agent/copilot-api/app/schemas.py`](agent/copilot-api/app/schemas.py),
> [`agent/copilot-api/app/verifier.py`](agent/copilot-api/app/verifier.py),
> and [`agent/copilot-api/evals/rubrics.py`](agent/copilot-api/evals/rubrics.py).
>
>**6. Eval-driven CI gate.** The golden suite has grown past the
> required 50 cases to **141 cases** across nine categories:
>
>| Category | Cases | What it pins |
> |---|---|---|
> | Wk1 regression | 34 | Tool routing, refusals, identity, immunizations — Week 1 behavior must not regress |
> | Extraction | varies | Lab panel parsing, intake completeness, image-only forms, dirty scans |
> | RAG | varies | BM25-only retrieval, vector-only retrieval, fused retrieval, rerank quality |
> | Citation | varies | bbox accuracy, verbatim quote match, chunk-in-corpus membership |
> | Refusal | varies | Out-of-scope queries, prompt injection in documents, PHI in question |
> | Integrity | varies | Lab writeback transactional integrity, idempotency, status semantics |
> | Critic | 4 | Critic accept / warn / reject branches |
> | Medication list | 5 | Happy path, dirty scan, dose ambiguity, reconciliation match / mismatch |
> | Graph end-to-end | varies | Full supervisor → workers → verifier chain |
>
>All rubrics are **boolean, deterministic functions** — no
> LLM-as-judge anywhere in the gate. The rubrics, with their pass-rate
> floors, are:
>
>```json
> {
>   "schema_valid":                          0.98,
>   "citation_present":                      0.98,
>   "factually_consistent":                  0.95,
>   "safe_refusal":                          1.00,
>   "no_phi_in_logs":                        1.00,
>   "integrity_writeback_present":           1.00,
>   "integrity_no_dup":                      1.00,
>   "integrity_status_preliminary":          1.00,
>   "integrity_writeback_gated_off_in_prod": 1.00,
>   "integrity_uses_collection_date":        1.00,
>   "critic_verdict":                        0.95,
>   "medication_list_reconciled":            1.00
> }
> ```
>
>The build fails if any rubric drops below its floor or regresses by
> more than 5%. CI runs on every PR via
> [`.github/workflows/eval-gate.yml`](.github/workflows/eval-gate.yml);
> a pre-push hook in
> [`.pre-commit-config.yaml`](.pre-commit-config.yaml) runs a 10-case
> smoke locally so a regression is caught before it hits CI. A nightly
> live-smoke workflow at
> [`.github/workflows/eval-gate-live.yml`](.github/workflows/eval-gate-live.yml)
> re-runs a 10-case slice against real Anthropic / Voyage / Cohere
> APIs to catch vendor drift. Code:
> [`agent/copilot-api/evals/`](agent/copilot-api/evals/) —
> `runner.py`, `rubrics.py`, `floor.json`, `case_schema.json`,
> `cases/`.
>
>**7. Observability and cost tracking.** Every encounter writes a
> Langfuse trace via
> [`agent/copilot-api/app/observability.py`](agent/copilot-api/app/observability.py)
> with one span per supervisor decision and one per worker node. Each
> trace records: tool sequence, latency by step, token usage, dollar
> cost per provider, retrieval hit count, extraction confidence, and
> the final eval outcome. Trace IDs join to OpenEMR's `agent_turn`
> audit row so any clinician's question can be replayed end-to-end.
>
>No raw PHI ever reaches Langfuse: `patient_uuid` is hashed, names
> and SSNs are redacted at the trace boundary, and claim text that
> contains clinical-action prose is dropped by the verifier before
> the trace is closed. A separate scrub pass strips filename PHI
> from upload logs (typed filenames like `Margaret Chen lipid panel.pdf`
> are redacted to a fixture-key hash before they reach the logger).
>
>Cost and latency analysis lives in
> [`cost_analysis_Wk2.md`](cost_analysis_Wk2.md) (per-turn cost
> breakdown across Sonnet vision, Haiku synthesis, Voyage embeddings,
> Cohere rerank; projections at 100 / 1K / 10K / 100K users; p50/p95
> latencies). The helper that pulls real Langfuse traces and computes
> the percentiles is at
> [`latency_percentiles.py`](latency_percentiles.py); run it against
> a recent time window to refresh the report.
>
>**Hard-gate self-test.** A regression dry-run is committed at
> [`agent/copilot-api/evals/regression_dry_run.md`](agent/copilot-api/evals/regression_dry_run.md):
> we intentionally introduced a verifier-rule regression, confirmed
> the pre-push hook blocked the local commit, then pushed it and
> watched the GitHub Actions eval-gate fail the PR. The plant-and-revert
> evidence is documented step by step.
>
>#### Extensions (above the Core bar)
>
>- **Critic agent.** A standalone `critic_node` runs after synthesis
>   and before verification. It re-reads the synthesizer's output
>   against the supplied evidence and the deterministic safety rules
>   (no uncited dose-change suggestions, no clinical action prose
>   without an authoritative source, etc.). On reject it rewrites
>   `llm_output` to a safe refusal before the verifier sees it; on
>   warn it tags the response with a warning chip; on accept it
>   passes through. The `critic_verdict` rubric has a 95% floor so
>   regressions in critic behavior fail the gate. Code:
>   [`agent/copilot-api/app/graph/critic.py`](agent/copilot-api/app/graph/critic.py).
>
>- **Click-to-source UI for citation snippets.** The Co-Pilot card
>   wires every source chip to a preview drawer that loads the
>   original PDF and draws the saved bbox at the cited page. The
>   PDF viewer is a vendored, SRI-pinned copy of PDF.js so the
>   page loads with no third-party CDN dependency. Code: the drawer
>   implementation lives inside
>   [`interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/js/copilot.js`](interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/js/copilot.js)
>   (search for `PDF.js click-to-source preview drawer` near line 401),
>   backed by the vendored viewer at
>   [`public/assets/vendor/pdfjs/`](interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/vendor/pdfjs/).
>
>- **Third document type — medication list.** Beyond lab PDFs and
>   intake forms, the agent ingests medication-list documents (typed,
>   handwritten, and dirty-scan variants) into the same Pydantic
>   extraction pipeline. A new gateway endpoint reconciles the
>   extracted list against the patient's active OpenEMR
>   `prescriptions` table and returns a side-by-side diff classified
>   as confirmed / newly_listed / possibly_discontinued. Code:
>   [`agent/copilot-api/app/extractors/medication_list.py`](agent/copilot-api/app/extractors/medication_list.py),
>   [`interface/modules/custom_modules/oe-module-clinical-copilot/public/api/medication_reconciliation.php`](interface/modules/custom_modules/oe-module-clinical-copilot/public/api/medication_reconciliation.php).
>
>#### Stretch (above Extension)
>
>- **Lab trend chart widget.** A trends panel below the Co-Pilot card
>   queries Co-Pilot-extracted `procedure_result` rows for the active
>   patient, groups by LOINC, and renders one mini SVG chart per
>   analyte with collected-date on the x-axis and abnormal-flag color
>   coding. The endpoint authenticates with the same session-cookie +
>   ACL `patients/med` + patient-scope-bind posture used by the rest
>   of the module; queries are parameterized; the widget hides itself
>   when no Co-Pilot-extracted labs exist. Code:
>   [`interface/modules/custom_modules/oe-module-clinical-copilot/public/api/lab_trends.php`](interface/modules/custom_modules/oe-module-clinical-copilot/public/api/lab_trends.php),
>   [`public/assets/js/lab_trends.js`](interface/modules/custom_modules/oe-module-clinical-copilot/public/assets/js/lab_trends.js).
>
>- **Contextual retrieval improvements.** Anthropic contextual
>   retrieval (per-chunk summary prepended to the BM25 token stream),
>   Reciprocal Rank Fusion in place of max-score, a clinical synonym
>   query rewriter, and domain-specific source filters for retrieval
>   are all shipped — see the RAG section above.
>
>#### Common pitfalls — how we avoided each
>
>- **VLM answer without schema validation or source metadata.** No
>   VLM response is allowed to leave the extractor unparsed. Every
>   extracted field flows through a Pydantic schema that requires a
>   `SourcePacket`; the verifier rule
>   [`citation_present`](agent/copilot-api/evals/rubrics.py) drops
>   any claim with no `source_ids`, and `quote_verbatim_in_pdf`
>   confirms the claim's text appears in the cited PDF before it
>   reaches the user.
>
>- **Black-box supervisor.** The supervisor is a deterministic set of
>   routing functions on the LangGraph's conditional edges — no LLM
>   hop, no hidden state. Every routing decision is appended to
>   `state.supervisor_routing_log` and emitted as a Langfuse span, so
>   each handoff between workers is logged, replayable, and labeled
>   with the rule that fired.
>
>- **LLM-as-judge.** All twelve rubric categories are **boolean
>   deterministic functions** in
>   [`agent/copilot-api/evals/rubrics.py`](agent/copilot-api/evals/rubrics.py).
>   They run offline, with no LLM call, against a frozen golden set;
>   a failure points at a specific case file and a specific rubric,
>   not a free-text judge score. The runner is
>   [`evals/runner.py`](agent/copilot-api/evals/runner.py).
>
>- **PHI in observability.** A multi-layer PHI scrub runs at four
>   points: (a) trace inputs to Langfuse — patient_uuid is hashed,
>   names / SSN / phone / MRN are redacted before any payload leaves
>   the sidecar; (b) LLM responses — the verifier strips clinical
>   action prose that names a patient; (c) eval CI logs — `stderr` /
>   `stdout` are scanned for PHI patterns before a test is allowed to
>   pass; (d) corpus ingestion — chunks contain only de-identified
>   guideline text, with a copyright-tripwire scan that fails the
>   build if a copyrighted phrase is detected. The demo and all
>   fixtures use synthetic data only (`Margaret Chen`, `Maria G.`,
>   etc.).
>
>---
>
>### Surprise Challenge — Modernize the Patient Dashboard
>
>The Week 2 surprise track ports OpenEMR's legacy PHP patient summary
> to a modern presentation layer that consumes OpenEMR's existing
> **FHIR R4 API** as a read-only data layer. The backend is untouched —
> no PHP edits, no SQL migrations, no Docker changes — and the legacy
> dashboard continues to work side by side with the new SPA.
>
>The new dashboard lives at [`dashboard-modern/`](dashboard-modern/)
> and is reachable from the deployed app's SMART app card on the
> patient summary; it also has a standalone-launch fallback.
>
>**Stack.**
>
>| Layer | Choice |
> |---|---|
> | Build tool | Vite 8 |
> | UI | React 19 + TypeScript strict + `noUncheckedIndexedAccess` |
> | SMART / OAuth | `fhirclient` v2 (SMART Health IT) |
> | FHIR types | `@types/fhir/r4` |
> | Runtime FHIR validation | Zod schemas at the boundary |
> | Server-state cache | TanStack Query v5 |
> | Routing | React Router v6 |
> | Styling | Tailwind CSS v4 + shadcn/ui copies |
> | Tests | Vitest + React Testing Library + MSW + Playwright |
>
>The full framework defense — alternatives evaluated, what we gained
> by moving off PHP, what we traded away, security posture, and parity
> gaps — lives in
> [`PATIENT_DASHBOARD_MIGRATION.md`](PATIENT_DASHBOARD_MIGRATION.md).
>
>**Feature parity.**
>
>- **Authentication via OAuth2 / OpenID Connect.** SMART-on-FHIR
>   v2.2.0 with PKCE S256, registered as a public client. EHR launch
>   from OpenEMR's built-in SMART app card is the primary path;
>   standalone launch via `/launch.html?iss=...&launch=...` is the
>   documented fallback. Logout is discovery-driven — the
>   `end_session_endpoint` is read from
>   `/oauth2/default/.well-known/openid-configuration` rather than
>   hard-coded; token revocation is wired conditionally on whether the
>   server advertises a `revocation_endpoint`. Code:
>   [`dashboard-modern/src/auth/`](dashboard-modern/src/auth/).
>
>- **Persistent patient header** — name, DOB, computed age, sex, MRN,
>   active status — sourced from FHIR `Patient` and rendered by
>   [`dashboard-modern/src/components/PatientHeader.tsx`](dashboard-modern/src/components/PatientHeader.tsx).
>
>- **Five clinical cards**, all reading live FHIR R4 data:
>   - **Allergies** — `AllergyIntolerance?patient=<id>` with NKDA-aware
>     rendering;
>     [`AllergiesCard.tsx`](dashboard-modern/src/components/cards/AllergiesCard.tsx).
>   - **Problem List** —
>     `Condition?patient=<id>&category=problem-list-item`, adapter-side
>     active-status filter;
>     [`ProblemListCard.tsx`](dashboard-modern/src/components/cards/ProblemListCard.tsx).
>   - **Medications** — `MedicationRequest?patient=<id>` filtered to
>     `intent === 'plan'`;
>     [`MedicationsCard.tsx`](dashboard-modern/src/components/cards/MedicationsCard.tsx).
>   - **Prescriptions** — `MedicationRequest?patient=<id>` filtered to
>     `intent === 'order'`, with prescriber names resolved through
>     per-participant `Practitioner` reads (concurrency capped at 3);
>     [`PrescriptionsCard.tsx`](dashboard-modern/src/components/cards/PrescriptionsCard.tsx).
>   - **Care Team** — `CareTeam?patient=<id>` with adapter-side
>     active-status filter and per-participant Practitioner
>     resolution;
>     [`CareTeamCard.tsx`](dashboard-modern/src/components/cards/CareTeamCard.tsx).
>
>  The medication/prescription split was confirmed live by a Phase 0
>   parity spike — see
>   [`dashboard-modern/MEDICATION_PARITY_SPIKE.md`](dashboard-modern/MEDICATION_PARITY_SPIKE.md).
>   Two FHIR-query probes (server-side status filtering and
>   `_include`) were also run live against OpenEMR; both outcomes
>   shaped the adapter design and are documented in
>   [`dashboard-modern/FHIR_QUERY_PROBES.md`](dashboard-modern/FHIR_QUERY_PROBES.md).
>
>- **Sixth section — Lab Results.** Most recent 10 `Observation`
>   resources filtered to `category=laboratory`, with H / L / HH / LL
>   abnormal-interpretation badges. Code:
>   [`LabResultsCard.tsx`](dashboard-modern/src/components/cards/LabResultsCard.tsx).
>
>**Read-only by enforcement.** A Playwright contract test
> ([`dashboard-modern/tests/contracts/no-mutation.spec.ts`](dashboard-modern/tests/contracts/no-mutation.spec.ts))
> intercepts every request the SPA makes and fails the build if any
> non-`GET` lands on `/apis/default/`. The whitelist for the OAuth
> token endpoint (and the optional revocation endpoint) is read from
> OIDC discovery at test setup, so the contract is self-correcting
> for any deployment.
>
>**End-to-end FHIR validation.** Every FHIR response is parsed
> through a Zod schema before any view-model adapter sees it; the UI
> never touches a raw FHIR resource. If OpenEMR changes a payload
> shape, the failure surfaces at the boundary with a clear error
> instead of garbling a render three layers deep.
>
>**No PHI in logs or test artifacts.** A `redact()` pass strips
> `access_token`, `refresh_token`, `id_token`, `Authorization`, plus
> PHI keys (`name`, `birthDate`, `mrn`, `ssn`, etc.) from any object
> before it crosses a logging boundary; no fixture or screenshot in
> the repo uses real patient data.
>
>---
>
>**Week1-AgentForge Fork:** This is a custom fork of [OpenEMR](https://github.com/openemr/openemr) developed during the [Gauntlet AgentForge](https://gauntletai.com) bootcamp. It adds a **Clinical Co-Pilot** AI module that surfaces verifier-gated patient briefings — identity, active problems, medications, allergies, recent labs, and immunizations — directly inside the OpenEMR patient chart via a Claude-powered FastAPI sidecar.
>
> **Thesis:** *A clinical agent intentionally constrained — read-only, current-patient, source-cited, verifier-gated, observable, and deployed — because in a clinical context the trustworthy 30% beats the impressive 80%.*
>
> **What the Co-Pilot does:**
>- Renders a read-only briefing card inside any patient chart, source-cited at the claim level.
> - Supports **7 first-class use cases**: pre-room brief, what changed, medication check, allergy check, recent abnormal labs, immunization history, and free-text chart follow-up.
> - LLM tool planning: the sidecar `POST /v1/tool-plan` chooses among **6 read-only tools** (`get_patient_identity`, `get_active_problems`, `get_active_medications`, `get_allergy_list`, `get_recent_labs`, `get_immunization_history`); OpenEMR executes them inside the authenticated current-patient gateway.
> - Free-text follow-up: physician can ask a chart-scoped question (e.g., *"What dose of lisinopril?"*) and gets a verifier-gated answer with click-through source chips. Clinical-action and other-patient questions are refused at the gateway before tool planning or LLM synthesis.
> - Source chip popovers: every cited claim chip opens a metadata card (table, field, observed-at, freshness) with an optional "Open record" deep-link.
> - Deterministic verifier with 11 rules (source attribution, patient binding, active-status, trend, blank-vs-negative, refusal scope, cross-patient, stale-data labeling, sensitive-data caveat, lists/prescriptions conflict surfacing) — see [agent/copilot-api/app/verifier.py](agent/copilot-api/app/verifier.py).
> - Sidecar auth: shared-secret **and** per-request HMAC task token bound to `patient_uuid_hash` (validated at the sidecar; expired tokens denied).
> - Clinician feedback chips (Helpful / Missing data / Incorrect / Too slow / Source unclear) post to Langfuse as scored trace events; `trace_id` joins to the OpenEMR `agent_turn` audit row.
> - 71/71 pytest + 34/34 eval cases passing offline (including router refusals, tool selection, tool failure, patient-override arguments, and immunization-history grounding).
>
> | Component | Location |
>|---|---|
> | OpenEMR module (PHP) | `interface/modules/custom_modules/oe-module-clinical-copilot/` |
> | AI sidecar (Python/FastAPI) | `agent/copilot-api/` |
> | Eval cases + runner | `agent/copilot-api/evals/` |
> | Demo data seed (synthetic) | [`agent/copilot-api/demo/seed_demo_patient.sql`](agent/copilot-api/demo/seed_demo_patient.sql) |
> | Week 2 architecture doc | [`W2_ARCHITECTURE.md`](W2_ARCHITECTURE.md) |
> | **AI Cost Analysis** (per-turn + 100 / 1K / 10K / 100K users) | Wk2 multimodal breakdown + latency canary at [`cost_analysis_Wk2.md`](cost_analysis_Wk2.md) (Wk1 cost notes are bundled inside the Wk2 doc for comparison). |
> | Audit & user docs | [`AUDIT.md`](AUDIT.md), [`Users.md`](Users.md) |
> | Surprise dashboard (React 19 SPA) | [`dashboard-modern/`](dashboard-modern/), defense in [`PATIENT_DASHBOARD_MIGRATION.md`](PATIENT_DASHBOARD_MIGRATION.md) |
> |                                                              |                                                              |
>
> Upstream: [openemr/openemr](https://github.com/openemr/openemr) — all original OpenEMR documentation follows below.

---

[![Syntax Status](https://github.com/openemr/openemr/actions/workflows/syntax.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/syntax.yml)
[![Styling Status](https://github.com/openemr/openemr/actions/workflows/styling.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/styling.yml)
[![Testing Status](https://github.com/openemr/openemr/actions/workflows/test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/test.yml)
[![JS Unit Testing Status](https://github.com/openemr/openemr/actions/workflows/js-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/js-test.yml)
[![PHPStan](https://github.com/openemr/openemr/actions/workflows/phpstan.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/phpstan.yml)
[![Rector](https://github.com/openemr/openemr/actions/workflows/rector.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/rector.yml)
[![ShellCheck](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml)
[![Docker Compose Linting](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml)
[![Dockerfile Linting](https://github.com/openemr/openemr/actions/workflows/hadolint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/hadolint.yml)
[![Isolated Tests](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml)
[![Inferno Certification Test](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml)
[![Composer Checks](https://github.com/openemr/openemr/actions/workflows/composer.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer.yml)
[![Composer Require Checker](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml)
[![API Docs Freshness Checks](https://github.com/openemr/openemr/actions/workflows/api-docs.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/api-docs.yml)
[![codecov](https://codecov.io/gh/openemr/openemr/graph/badge.svg?token=7Eu3U1Ozdq)](https://codecov.io/gh/openemr/openemr)

[![Backers on Open Collective](https://opencollective.com/openemr/backers/badge.svg)](#backers) [![Sponsors on Open Collective](https://opencollective.com/openemr/sponsors/badge.svg)](#sponsors)

# OpenEMR

[OpenEMR](https://open-emr.org) is a Free and Open Source electronic health records and medical practice management application. It features fully integrated electronic health records, practice management, scheduling, electronic billing, internationalization, free support, a vibrant community, and a whole lot more. It runs on Windows, Linux, Mac OS X, and many other platforms.

### Contributing

OpenEMR is a leader in healthcare open source software and comprises a large and diverse community of software developers, medical providers and educators with a very healthy mix of both volunteers and professionals. [Join us and learn how to start contributing today!](https://open-emr.org/wiki/index.php/FAQ#How_do_I_begin_to_volunteer_for_the_OpenEMR_project.3F)

> Already comfortable with git? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for quick setup instructions and requirements for contributing to OpenEMR by resolving a bug or adding an awesome feature 😊.

### Support

Community and Professional support can be found [here](https://open-emr.org/wiki/index.php/OpenEMR_Support_Guide).

Extensive documentation and forums can be found on the [OpenEMR website](https://open-emr.org) that can help you to become more familiar about the project 📖.

### Reporting Issues and Bugs

Report these on the [Issue Tracker](https://github.com/openemr/openemr/issues). If you are unsure if it is an issue/bug, then always feel free to use the [Forum](https://community.open-emr.org/) and [Chat](https://www.open-emr.org/chat/) to discuss about the issue 🪲.

### Reporting Security Vulnerabilities

Check out [SECURITY.md](.github/SECURITY.md)

### API

Check out [API_README.md](API_README.md)

### Docker

Check out [DOCKER_README.md](DOCKER_README.md)

### FHIR

Check out [FHIR_README.md](FHIR_README.md)

### For Developers

If using OpenEMR directly from the code repository, then the following commands will build OpenEMR (Node.js version 24.* is required) :

```shell
composer install --no-dev
npm install
npm run build
composer dump-autoload -o
```

### Contributors

This project exists thanks to all the people who have contributed. [[Contribute]](CONTRIBUTING.md).
<a href="https://github.com/openemr/openemr/graphs/contributors"><img src="https://opencollective.com/openemr/contributors.svg?width=890" /></a>


### Sponsors

Thanks to our [ONC Certification Major Sponsors](https://www.open-emr.org/wiki/index.php/OpenEMR_Certification_Stage_III_Meaningful_Use#Major_sponsors)!


### License

[GNU GPL](LICENSE)
