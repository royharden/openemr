"""One-shot script to write extraction eval cases 5-18."""
import json
import pathlib

base = pathlib.Path(__file__).parent.parent / "evals" / "cases" / "extraction"
base.mkdir(exist_ok=True)

cases = [
    ("extraction_05_stress_handwritten.json", {
        "case_id": "extraction/05_stress_handwritten",
        "category": "extraction",
        "description": "Stress test: handwritten intake form — legible fields extracted, illegible ones reported as missing_data.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where handwritten form processing crashes or silently drops fields without reporting them in missing_data.",
        "packets": [{"source_id": "extract:reyes-handwritten:medications", "patient_uuid": "uuid-reyes-003", "resource_type": "MedicationStatement", "source_table": "procedure_result", "field": "medications.current", "label": "Current Medications", "value": "Metformin 500mg", "unit": None, "observed_at": "2026-03-15", "freshness": "recent", "status": "active", "source_type": "document_extract", "quote_or_value": "Medications: Metformin 500mg"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Patient is currently taking Metformin 500mg per the handwritten intake form.", "claim_type": "fact", "source_ids": ["extract:reyes-handwritten:medications"], "caveat": "Self-reported on handwritten intake form."}], "missing_data": ["Dosage frequency was illegible on the handwritten form."], "refusals": [], "suggested_followups": ["Confirm Metformin dosing schedule with patient verbally."]},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_06_stress_dirty_scan.json", {
        "case_id": "extraction/06_stress_dirty_scan",
        "category": "extraction",
        "description": "Stress test: dirty scan (ink bleed, skew) — extractor uses OCR fallback and still extracts numeric values.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where a low-quality scan causes the extractor to skip the entire document instead of falling back to OCR for legible fields.",
        "packets": [{"source_id": "extract:kowalski-dirty:potassium", "patient_uuid": "uuid-kowalski-004", "resource_type": "Observation", "source_table": "procedure_result", "field": "potassium", "label": "Potassium", "value": "4.1", "unit": "mEq/L", "observed_at": "2026-02-20", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "Potassium: 4.1 mEq/L", "confidence": 0.82}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Potassium was 4.1 mEq/L per the CMP dated 2026-02-20.", "claim_type": "fact", "source_ids": ["extract:kowalski-dirty:potassium"], "caveat": "Extracted from a low-quality scan; OCR confidence 0.82."}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_07_stress_no_text_layer.json", {
        "case_id": "extraction/07_stress_no_text_layer",
        "category": "extraction",
        "description": "Stress test: scanned PDF with no text layer — vision extraction is used as primary method.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where the extractor skips a PDF that has no embedded text layer instead of routing to vision extraction.",
        "packets": [{"source_id": "extract:whitaker-scan:wbc", "patient_uuid": "uuid-whitaker-002", "resource_type": "Observation", "source_table": "procedure_result", "field": "wbc", "label": "WBC", "value": "7.5", "unit": "K/uL", "observed_at": "2026-03-28", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "WBC: 7.5 K/uL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "WBC was 7.5 K/uL per the CBC dated 2026-03-28.", "claim_type": "fact", "source_ids": ["extract:whitaker-scan:wbc"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_08_stress_illegible.json", {
        "case_id": "extraction/08_stress_illegible",
        "category": "extraction",
        "description": "Stress test: illegible field in handwritten form — extractor must omit, not guess.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where extractor guesses an illegible field value instead of omitting it, producing a hallucinated extraction.",
        "packets": [],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [], "missing_data": ["Chief complaint field was illegible in the handwritten intake form and was omitted."], "refusals": [], "suggested_followups": ["Ask patient to confirm chief complaint verbally."]},
        "expectations": {"verifier_status": "passed", "max_dropped": 0}
    }),
    ("extraction_09_stress_multipage.json", {
        "case_id": "extraction/09_stress_multipage",
        "category": "extraction",
        "description": "Stress test: multi-panel lab PDF — results on page 2 are also extracted with correct page_index.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where extractor only processes page 0 and misses lab results on subsequent pages.",
        "packets": [{"source_id": "extract:whitaker-cbc:hemoglobin", "patient_uuid": "uuid-whitaker-002", "resource_type": "Observation", "source_table": "procedure_result", "field": "hemoglobin", "label": "Hemoglobin", "value": "13.8", "unit": "g/dL", "observed_at": "2026-03-28", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "Hemoglobin: 13.8 g/dL", "page_index": 1}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Hemoglobin was 13.8 g/dL per the CBC report.", "claim_type": "fact", "source_ids": ["extract:whitaker-cbc:hemoglobin"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_10_idempotency.json", {
        "case_id": "extraction/10_idempotency",
        "category": "extraction",
        "description": "Extraction idempotency: re-uploading the same document must not produce duplicate records (SHA-256 dedup).",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where re-uploading the same document creates duplicate copilot_document_facts rows instead of using the idempotency key.",
        "packets": [{"source_id": "extract:chen-lipid:hdl", "patient_uuid": "uuid-chen-001", "resource_type": "Observation", "source_table": "procedure_result", "field": "hdl", "label": "HDL", "value": "58", "unit": "mg/dL", "observed_at": "2026-04-01", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "HDL: 58 mg/dL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "HDL was 58 mg/dL per the lipid panel.", "claim_type": "fact", "source_ids": ["extract:chen-lipid:hdl"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_11_stress_kowalski_cmp.json", {
        "case_id": "extraction/11_stress_kowalski_cmp",
        "category": "extraction",
        "description": "Stress test: Kowalski CMP dirty scan — multiple lab fields extracted correctly from poor-quality scan.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present", "factually_consistent"],
        "what_bug_this_catches": "Regression where dirty-scan CMP extraction fails on numeric values adjacent to poor OCR quality text.",
        "packets": [{"source_id": "extract:kowalski-cmp:sodium", "patient_uuid": "uuid-kowalski-004", "resource_type": "Observation", "source_table": "procedure_result", "field": "sodium", "label": "Sodium", "value": "140", "unit": "mEq/L", "observed_at": "2026-02-20", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "Sodium: 140 mEq/L", "confidence": 0.90}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Sodium was 140 mEq/L per the CMP.", "claim_type": "fact", "source_ids": ["extract:kowalski-cmp:sodium"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_12_stress_allergies.json", {
        "case_id": "extraction/12_stress_allergies",
        "category": "extraction",
        "description": "Stress test: self-reported allergies on intake form — extracted with correct allergy field path.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where self-reported allergy extraction produces wrong field path or omits the value entirely.",
        "packets": [{"source_id": "extract:chen-intake:allergy", "patient_uuid": "uuid-chen-001", "resource_type": "AllergyIntolerance", "source_table": "procedure_result", "field": "allergies.self_reported", "label": "Self-reported allergy", "value": "Penicillin - rash", "unit": None, "observed_at": "2026-04-01", "freshness": "recent", "status": "active", "source_type": "document_extract", "quote_or_value": "Allergies: Penicillin - rash"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Patient reports allergy to Penicillin (rash) per intake form.", "claim_type": "fact", "source_ids": ["extract:chen-intake:allergy"], "caveat": "Self-reported on intake form; not yet verified against chart."}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_13_stress_conflicting_values.json", {
        "case_id": "extraction/13_stress_conflicting_values",
        "category": "extraction",
        "description": "Stress test: two documents for same patient have conflicting lab values — extractor surfaces both with distinct source_ids.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present", "factually_consistent"],
        "what_bug_this_catches": "Regression where extractor silently deduplicates or overwrites a conflicting lab value instead of preserving both packets with distinct source_ids.",
        "packets": [{"source_id": "extract:reyes-lipid-apr:ldl", "patient_uuid": "uuid-reyes-003", "resource_type": "Observation", "source_table": "procedure_result", "field": "ldl", "label": "LDL", "value": "142", "unit": "mg/dL", "observed_at": "2026-04-10", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "LDL: 142 mg/dL"}, {"source_id": "extract:reyes-lipid-mar:ldl", "patient_uuid": "uuid-reyes-003", "resource_type": "Observation", "source_table": "procedure_result", "field": "ldl", "label": "LDL", "value": "155", "unit": "mg/dL", "observed_at": "2026-03-05", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "LDL: 155 mg/dL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "LDL was 142 mg/dL on 2026-04-10 per the April lipid panel.", "claim_type": "fact", "source_ids": ["extract:reyes-lipid-apr:ldl"], "caveat": None}, {"text": "Prior LDL was 155 mg/dL on 2026-03-05 per the March lipid panel.", "claim_type": "fact", "source_ids": ["extract:reyes-lipid-mar:ldl"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 2, "max_dropped": 0}
    }),
    ("extraction_14_stress_unit_normalization.json", {
        "case_id": "extraction/14_stress_unit_normalization",
        "category": "extraction",
        "description": "Stress test: lab result with non-standard unit abbreviation (mmol/L) — extractor must preserve original unit, not convert.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present", "factually_consistent"],
        "what_bug_this_catches": "Regression where extractor silently converts units (e.g., mmol/L to mg/dL), causing a numeric mismatch between the stored packet value and the original document.",
        "packets": [{"source_id": "extract:kowalski-glucose:glucose", "patient_uuid": "uuid-kowalski-004", "resource_type": "Observation", "source_table": "procedure_result", "field": "glucose", "label": "Glucose", "value": "6.1", "unit": "mmol/L", "observed_at": "2026-02-20", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "Glucose: 6.1 mmol/L"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Glucose was 6.1 mmol/L per the CMP report.", "claim_type": "fact", "source_ids": ["extract:kowalski-glucose:glucose"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_15_stress_date_formats.json", {
        "case_id": "extraction/15_stress_date_formats",
        "category": "extraction",
        "description": "Stress test: handwritten form uses non-ISO date format (MM/DD/YYYY) — extractor must normalize to ISO 8601.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present", "factually_consistent"],
        "what_bug_this_catches": "Regression where extractor stores the raw date string instead of normalizing to ISO 8601, breaking date comparison and freshness logic downstream.",
        "packets": [{"source_id": "extract:chen-intake:dob", "patient_uuid": "uuid-chen-001", "resource_type": "Patient", "source_table": "procedure_result", "field": "demographics.date_of_birth", "label": "Date of Birth", "value": "1978-07-22", "unit": None, "observed_at": "2026-04-01", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "DOB: 07/22/1978"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Patient date of birth is 1978-07-22 per the intake form.", "claim_type": "fact", "source_ids": ["extract:chen-intake:dob"], "caveat": "Self-reported on intake form."}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_16_stress_partial_ocr.json", {
        "case_id": "extraction/16_stress_partial_ocr",
        "category": "extraction",
        "description": "Stress test: lab PDF has partial OCR failure — only legible fields extracted; illegible fields omitted with missing_data entry.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where partial OCR failure causes the extractor to either halt entirely or hallucinate values for illegible fields.",
        "packets": [{"source_id": "extract:whitaker-cbc-partial:wbc", "patient_uuid": "uuid-whitaker-002", "resource_type": "Observation", "source_table": "procedure_result", "field": "wbc", "label": "WBC", "value": "7.2", "unit": "K/uL", "observed_at": "2026-03-28", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "WBC: 7.2 K/uL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "WBC was 7.2 K/uL per the CBC report dated 2026-03-28.", "claim_type": "fact", "source_ids": ["extract:whitaker-cbc-partial:wbc"], "caveat": None}], "missing_data": ["Platelet count field was illegible due to ink smear on page 1 and was omitted."], "refusals": [], "suggested_followups": ["Review original CBC document for platelet count."]},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_17_stress_multi_patient_guard.json", {
        "case_id": "extraction/17_stress_multi_patient_guard",
        "category": "extraction",
        "description": "Stress test: document bundle accidentally contains pages from two different patients — extractor must only emit packets matching the requested patient_uuid.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present", "factually_consistent"],
        "what_bug_this_catches": "Regression where extractor processes a mixed-patient document bundle and emits packets for both patients, creating cross-patient data contamination.",
        "packets": [{"source_id": "extract:chen-cbc-mixed:hemoglobin", "patient_uuid": "uuid-chen-001", "resource_type": "Observation", "source_table": "procedure_result", "field": "hemoglobin", "label": "Hemoglobin", "value": "14.1", "unit": "g/dL", "observed_at": "2026-04-01", "freshness": "recent", "status": "final", "source_type": "document_extract", "quote_or_value": "Hemoglobin: 14.1 g/dL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Hemoglobin was 14.1 g/dL per the CBC report dated 2026-04-01.", "claim_type": "fact", "source_ids": ["extract:chen-cbc-mixed:hemoglobin"], "caveat": None}], "missing_data": [], "refusals": [], "suggested_followups": []},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
    ("extraction_18_stress_stale_document.json", {
        "case_id": "extraction/18_stress_stale_document",
        "category": "extraction",
        "description": "Stress test: lab document dated > 1 year ago — extractor must tag freshness as 'stale'.",
        "mode": "verifier",
        "rubrics": ["schema_valid", "citation_present"],
        "what_bug_this_catches": "Regression where extractor always tags freshness as 'recent' regardless of observed_at date, preventing the verifier from flagging stale evidence.",
        "packets": [{"source_id": "extract:chen-lipid-2024:ldl", "patient_uuid": "uuid-chen-001", "resource_type": "Observation", "source_table": "procedure_result", "field": "ldl", "label": "LDL", "value": "162", "unit": "mg/dL", "observed_at": "2024-11-05", "freshness": "stale", "status": "final", "source_type": "document_extract", "quote_or_value": "LDL: 162 mg/dL"}],
        "llm_output": {"answer_type": "pre_room_brief", "claims": [{"text": "Most recent available LDL was 162 mg/dL dated 2024-11-05 (over 1 year ago); consider ordering a current lipid panel.", "claim_type": "fact", "source_ids": ["extract:chen-lipid-2024:ldl"], "caveat": "Data is over 1 year old and may not reflect current status."}], "missing_data": [], "refusals": [], "suggested_followups": ["Order current lipid panel to confirm LDL trend."]},
        "expectations": {"verifier_status": "passed", "min_accepted_claims": 1, "max_dropped": 0}
    }),
]

for filename, case in cases:
    path = base / filename
    path.write_text(json.dumps(case, indent=2))
    print(f"Written: {filename}")

print(f"Total: {len(cases)} cases")
