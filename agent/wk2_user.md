# Week 2 User Profile — Dr. Lee, Family Medicine PCP

> **Companion to:** [`openemr/planning/Users_Wk1.md`](../planning/Users_Wk1.md) (Wk1 baseline — Dr. Sarah Clark, pre-room briefing).
> **Authored under:** Plan section 8 of `openemr/planning/Plan_wk2_Claude_Next04_2026-05-10_demo-and-fhir-closure.md`.
> **Purpose:** Justify the five RAG sources committed to the Wk2 corpus by anchoring each to a concrete question Dr. Lee asks the Co-Pilot in front of a real fixture patient. Without this anchor, the corpus choices are arbitrary.

Wk1 framed the user around the *between-rooms* window: 90 seconds to read the chart before walking in. Wk2 zooms in on what's *inside* that chart when the patient is new-to-this-clinic, the fax inbox is full of outside-lab PDFs, and the front desk just dropped a scanned intake form on the chart. The Wk1 user (Dr. Clark, established panel) has continuity. The Wk2 user (Dr. Lee) has paper.

---

## Persona

**Dr. Lee, Family Medicine PCP** — urban community clinic, mixed-insurance patient panel, OpenEMR-based.

| Attribute | Value |
|---|---|
| Schedule | ~24 patients/day, 18-minute follow-up slots |
| Patient mix | New patients ~30%, established ~70%; high volume of outside-lab faxes |
| Pre-visit prep window | **3 minutes per chart**, between rooms |
| Where the prep time goes | Scanned faxes (outside-lab PDFs), scanned intake forms from the front desk, occasional handwritten medication lists |
| EHR experience | Power user; comfortable with OpenEMR's documents tab, lab review, FHIR endpoint |
| Pain point | The actionable information is in PDFs and image scans, not in OpenEMR's structured tables. She loses the first 2 of 3 minutes reading attachments instead of reasoning about them. |

### Why Dr. Lee and not Dr. Clark (Wk1)

Wk1 solved "what changed since last visit?" — a continuity problem that only matters when there *is* a last visit. Wk2 solves the upstream problem: **the patient's data is in the chart, but trapped in scans the EHR can't parse.** Dr. Lee is the Wk1 user one step earlier in the workflow — before the structured chart exists, when the only inputs are PDFs and image scans. The same physician archetype, different bottleneck.

### Why family medicine and not specialty

The five RAG sources span vaccines, lipid management, glycemic management, drug labels, and HTN evidence summaries — the **breadth of a PCP encounter**, not the depth of a single specialty. A cardiologist would never ask the Co-Pilot a vaccine question; an endocrinologist would never ask about ACIP. The breadth of the source list only makes sense for a PCP.

---

## Five questions Dr. Lee asks the Co-Pilot

Each question maps to one fixture patient (`openemr/agent/copilot-api/evals/fixtures/documents/`) and one RAG source. The fifth is cross-cutting — it exercises the corpus on a multi-source question Dr. Lee asks roughly once an hour.

### Q1 — Anne Chen, lipid panel → ACC/AHA 2026

- **Fixture:** `p01-chen-lipid-panel.pdf` + `p01-chen-intake-typed.pdf`
- **Question (verbatim, between rooms):** *"What's the right next step for this LDL?"*
- **Why she's asking:** Chen is a 64-year-old established patient. The lab PDF just came in from an outside lab. LDL is elevated. Dr. Lee needs to decide statin intensity *before* she walks in — Chen will ask "what does the lab say?" the moment the visit starts.
- **RAG source the Co-Pilot must hit:** **ACC/AHA 2026 Dyslipidemia Guideline** (locally-authored summary chunks in `openemr/agent/copilot-api/app/rag/ingestion/acc_aha_2026.py`).
- **What the summary chunks cover:** LDL targets by risk tier, statin intensity tiers (high/moderate/low), secondary-prevention add-on options (ezetimibe, PCSK9), monitoring cadence.
- **Out of the corpus on purpose:** procedural cardiology (cath, stents, CABG) — those are specialist territory and Dr. Lee would refer, not manage.

### Q2 — Sofia Reyes, HbA1c → ADA 2026

- **Fixture:** `p03-reyes-hba1c.png` + `p03-reyes-intake.png` (handwritten — OCR stress case)
- **Question:** *"Is her A1c controlled, and what should we adjust?"*
- **Why she's asking:** Reyes is a 70-year-old on metformin monotherapy. Her A1c PNG comes in from the outside lab, hand-annotated by the lab tech. Dr. Lee needs to know whether A1c is at her individualized target (the answer is age- and comorbidity-dependent — not a flat 7.0%) and what the next add-on should be if not.
- **RAG source the Co-Pilot must hit:** **ADA 2026 Standards of Care** (locally-authored summary chunks in `openemr/agent/copilot-api/app/rag/ingestion/ada_2026.py`).
- **What the summary chunks cover:** A1c targets by age and comorbidity, metformin starting and titration dosing, eGFR-based safety thresholds, GLP-1 and SGLT2 second-line considerations (cardio-renal benefit), and screening cadence.
- **Out of the corpus on purpose:** insulin pump management, CGM titration — endocrinology subspecialty work.

### Q3 — Marcus Whitaker, preventive visit → CDC ACIP

- **Fixture:** `p02-whitaker-cbc.pdf` + `p02-whitaker-intake.pdf`
- **Question:** *"Is Mr. Whitaker due for any vaccines?"*
- **Why she's asking:** Whitaker is 55, new to the clinic, here for an annual wellness exam. His intake PDF lists immunizations going back to childhood; the front desk could not enter them as structured records because the intake is a scanned PDF. Dr. Lee needs the Co-Pilot to extract the immunization history *and* cross-reference the CDC schedule to flag what's due (Tdap, shingles, pneumococcal, flu, COVID).
- **RAG source the Co-Pilot must hit:** **CDC ACIP Adult Immunization Schedule** (`openemr/agent/copilot-api/app/rag/ingestion/cdc_acip.py`).
- **What the corpus covers:** 8 immunization schedules fetched live at corpus-build time from the CDC, with bundled snippets as offline fallback.
- **Note on scope vs. Wk1:** Wk1 explicitly said the agent *does not* declare immunizations "overdue" — that was the v1 scoping choice. Wk2 reverses that for the ACIP-backed subset only: ACIP is an authoritative, citation-friendly source, so the Co-Pilot can now say "Tdap is due (last 2014)" with a chip pointing at the ACIP schedule. The Wk1 stance (no guideline recommendations) still holds for everything else in the corpus.

### Q4 — Tomas Kowalski, medication safety → openFDA

- **Fixture:** `p04-kowalski-cmp.pdf` + `p04-kowalski-intake.png` (dirty scan + mixed handwriting)
- **Question:** *"Is metformin still safe at his current eGFR?"*
- **Why she's asking:** Kowalski is 77, on metformin for ~10 years. His CMP comes in with an eGFR that's been drifting downward. Dr. Lee needs the official label language on renal cutoffs (not a paraphrase) before deciding whether to dose-reduce or switch.
- **RAG source the Co-Pilot must hit:** **openFDA drug label, metformin entry** (`openemr/agent/copilot-api/app/rag/ingestion/openfda.py` — 25 high-frequency PCP drug labels).
- **What the corpus covers:** Drug labels for the 25 most-prescribed PCP drugs (metformin, lisinopril, atorvastatin, amlodipine, levothyroxine, sertraline, omeprazole, …), with the warnings/contraindications/dosing-and-administration sections indexed.
- **Why the official label and not a guideline:** Renal cutoffs for metformin have legal weight on the label — Dr. Lee wants to see the actual contraindication wording, not a guideline paraphrase. openFDA is the only source in the corpus that carries label authority.

### Q5 — Cross-cutting, HTN + diabetes → HMS-LOE

- **Question:** *"What's the best add-on antihypertensive for a patient who also has diabetes?"*
- **Why she's asking:** This question pulls from two clinical domains at once. ADA covers diabetes; an HTN-specific guideline (JNC or AHA) would cover hypertension; but the *intersection* — "given comorbidity X, what's the best Y add-on?" — is what evidence summaries do well and what individual guidelines do badly.
- **RAG source the Co-Pilot must hit:** **HMS Library of Evidence (HMS-LOE)** (`openemr/agent/copilot-api/app/rag/ingestion/hms_loe.py` — 10 curated evidence summaries).
- **What the corpus covers:** Evidence-graded summaries for diabetes, HTN, hyperlipidemia, anticoagulation, asthma, pain, COPD, ACE cough, immunization catch-up.
- **Why HMS-LOE earns a seat:** ACC/AHA and ADA are vertical; HMS-LOE is horizontal across chronic disease. It catches the "comorbidity sweet spot" questions that fall between the vertical guidelines. Without it, Q5 would force the synthesis node to either pick one vertical guideline and ignore the other, or refuse.

---

## Out of scope (named explicitly)

These are excluded from the Wk2 corpus deliberately. When Dr. Lee asks a question that maps to one of these, the agent must **refuse cleanly with a "not in corpus" message**, not guess from general medical knowledge.

### 1. Cancer screening (USPSTF) — deferred to Wk3

The most obvious missing piece for a PCP corpus. Mammography, colonoscopy, lung CT, cervical cytology — all USPSTF territory, all extremely relevant to preventive-visit workflows. Held back from Wk2 deliberately because:

- USPSTF recommendations have nuance (grade A/B/C/D/I, age windows, risk-factor modifiers) that needs a clinician-review workflow before automating.
- Wk3 plan includes the clinician-review UI (pending/confirmed/rejected states for derived recommendations); USPSTF lands then.
- Building the agent's refusal muscle for "this is out of corpus" is itself valuable. If Dr. Lee asks "is Whitaker due for a colonoscopy?", the agent must say *"colorectal cancer screening is not in the Wk2 corpus — refer to USPSTF directly"* instead of hallucinating an age cutoff.

### 2. Specialist deep-dives

Out of scope for the same reason a PCP wouldn't manage them in-clinic:

- **Cardiology procedures** — cath, stent, CABG, electrophysiology. ACC/AHA summary chunks cover *PCP-relevant* lipid management only, not procedural decision-making.
- **Endocrinology subspecialty** — insulin pump titration, CGM management, thyroid nodule workup beyond TSH/FT4. ADA summary chunks cover *PCP-relevant* glycemic management only.
- **Oncology, rheumatology, nephrology subspecialty work** — not in any source.

If Dr. Lee asks "what's the right stent for Chen's LAD lesion?", the agent refuses.

### 3. Pediatric dosing

The CDC ACIP source includes the *child* immunization schedule (it's part of the 8 schedules ingested), so vaccine questions for pediatric patients work. But **pediatric drug dosing** is not in the openFDA subset — the 25 drug labels are PCP-adult-relevant (metformin, lisinopril, etc., dosed for adults). A question like "what's the right amoxicillin dose for a 15kg child?" must be refused, not guessed from the adult label.

---

## Why these five sources — one paragraph each

### CDC ACIP Adult Immunization Schedule

The only authoritative source for immunization cadence in the United States. Non-negotiable for any PCP workflow that touches preventive care. The ingestion module (`cdc_acip.py`) fetches 8 schedules live at corpus-build time, with bundled snippets as offline fallback — the corpus does not depend on CDC API availability at runtime. ACIP is also one of the few clinical sources that's both freely redistributable and frequently updated, which is why it earns the corpus seat over commercial alternatives.

### openFDA drug labels

Drug labels carry legal weight that no guideline does — when Dr. Lee asks about a metformin contraindication at low eGFR, she wants the label's exact warning language, not a paraphrase from a textbook. The 25-drug subset (`openfda.py`) covers ~80% of PCP prescription volume by frequency (statins, metformin, common antihypertensives, anticoagulants, common psychotropics, common GI drugs). openFDA is free, well-documented, and stable. The fetched labels are persisted into `corpus.db` at build time, so runtime retrieval does not depend on openFDA availability.

### HMS Library of Evidence (HMS-LOE)

Horizontal across chronic disease where ACC/AHA and ADA are vertical. The 10 curated summaries (`hms_loe.py`) bridge the comorbidity sweet spot — questions where the patient has two or more chronic conditions and the right answer depends on the interaction (Q5 above). Evidence summaries are also the right granularity for the 18-minute visit: they're shorter and more actionable than full guidelines, and they cite grades so Dr. Lee can judge confidence at a glance.

### ADA 2026 Standards of Care (locally-authored summary)

Added in Section 6.4 of the plan specifically to back the Reyes HbA1c fixture (Q2). Without it, the Co-Pilot has no authoritative source to ground glycemic-management answers — HMS-LOE has a diabetes entry but it's the comorbidity-intersection summary, not the full Standards of Care. **Important copyright posture:** the chunks committed to the corpus are **locally-authored summaries**, not copy-pasted ADA text. The `source_url` metadata points at the official ADA URL so Dr. Lee can read the original; the chunk body is original prose covering A1c targets, metformin dosing, eGFR safety, and GLP-1/SGLT2 add-on logic. The plan's `--check-corpus-copyright` flag (Section 6.4) enforces this at build time.

### ACC/AHA 2026 Dyslipidemia Guideline (locally-authored summary)

Added in the same Section 6.4 to back the Chen lipid fixture (Q1). Same copyright posture as ADA: locally-authored summary chunks covering LDL targets, statin intensity tiers, and secondary-prevention add-ons. `source_url` metadata points at the official ACC/AHA press release URL. **Not committed:** the full guideline body, any procedural cardiology content, or anything outside the PCP-relevant lipid-management subset.

---

## Considered and held — queued for Wk3

From `arcprep2/wk2_gemini_RAG_source_research.md` (11 candidate sources researched, 5 selected for Wk2):

| Source | Why held to Wk3 |
|---|---|
| **USPSTF** | Needs clinician-review workflow first (pending/confirmed/rejected states for derived recommendations). Wk3 plan includes that workflow; USPSTF lands then. |
| **UpToDate** | Subscription-gated; redistribution rights unclear. Wk3 to revisit under an institutional license if the project survives to a clinical pilot. |
| **Lexicomp** | Same as UpToDate — subscription and redistribution issues. The openFDA labels cover the same surface for the 25-drug subset; Lexicomp would extend coverage but isn't on a free path. |
| **NICE (UK National Institute for Health and Care Excellence)** | High-quality, free to access, but UK-pathway-oriented (NHS workflows, UK formulary). Wk3 question is whether the US-PCP-relevant subset is worth the curation effort. |
| **One other (declined for API lead time >3 days)** | Listed in Gemini's research; declined because the sprint timeline didn't allow for API onboarding. |

Wk3 corpus expansion is **contingent on the clinician-review workflow landing first**. Without it, expanding the corpus only expands the surface area where the agent might over-confidently summarize a recommendation the clinician hasn't vetted.

---

## How this file is used

- **By the demo runbook (`agentdocs/DEMO_RUNBOOK_Wk2.md`):** Section 2.3 narrates "three questions, three different sources" while the camera is on the Co-Pilot panel. The five questions above are the script.
- **By the eval suite:** Each of Q1–Q5 maps to at least one eval case under `openemr/agent/copilot-api/evals/fixtures/cases/`. The "out of scope" list maps to refusal cases (e.g., a USPSTF colonoscopy question must produce a `safe_refusal` rubric outcome).
- **By the post-Wk2 review:** This is the artifact the reviewer points to when asking "what user was Wk2 designed for, and why these five sources?"

---

## Traceability to architecture

| User constraint (this doc) | Wk2 architecture decision |
|---|---|
| 3-minute pre-visit window | Multimodal extraction must complete in <10s p95 per upload |
| Outside-lab PDFs as primary input | `upload_lab.php` + `intake_extractor_node` are the demo's main beats |
| Handwritten / dirty-scan stress cases | Reyes (p03) and Kowalski (p04) fixtures included for OCR robustness |
| ACC/AHA 2026 for Chen, ADA 2026 for Reyes | Section 6.4 adds locally-authored summary ingestion modules |
| Refuse cleanly on out-of-corpus questions | Verifier `safe_refusal` rubric floor at 100% |
| Copyright-safe corpus | `--check-corpus-copyright` pre-commit scan (plan Section 6.4) |
| PCP breadth, not specialist depth | Corpus deliberately spans 5 horizontal sources, no specialty depth |

If a Wk2 architecture decision can't be traced to a row in this table, it doesn't belong in Wk2.

---

## End of profile
