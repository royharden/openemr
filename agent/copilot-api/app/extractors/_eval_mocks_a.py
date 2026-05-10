"""Deterministic mock vision extractor for COPILOT_EVAL_MODE=1.

Team C integrates this into app/extractors/_eval_mocks.py.
Used by: lab_pdf.py and intake_form.py when COPILOT_EVAL_MODE env var is "1".

Each fixture keyed by document_sha256 prefix (first 8 hex chars) returns
a pre-baked list of (field_name, value, unit, page_index, bbox, quote) tuples
so the eval gate never hits Anthropic Vision API.
"""

from __future__ import annotations

import os

_EVAL_MODE = os.environ.get("COPILOT_EVAL_MODE", "0") == "1"


# ---------------------------------------------------------------------------
# Fixture registry  — keyed by sha256[:8] of the committed fixture files.
# (Run sha256sum on each file to refresh if fixtures are regenerated.)
# ---------------------------------------------------------------------------

# shape: list of (name, value, unit, flag, reference_range, loinc_code, page_index, bbox, quote)
_LAB_FIXTURES: dict[str, list[tuple[str, object, str | None, str | None, str | None, str | None, int, tuple[float, float, float, float] | None, str | None]]] = {
    # p01-chen-lipid-panel.pdf
    "chen_lipid": [
        ("cholesterol_total", 198.0, "mg/dL", "N", "<200", "2093-3", 0, (0.10, 0.30, 0.55, 0.34), "Total Cholesterol: 198 mg/dL"),
        ("ldl", 122.0, "mg/dL", "N", "<130", "13457-7", 0, (0.10, 0.36, 0.55, 0.40), "LDL: 122 mg/dL"),
        ("hdl", 58.0, "mg/dL", "N", ">40", "2085-9", 0, (0.10, 0.42, 0.55, 0.46), "HDL: 58 mg/dL"),
        ("triglycerides", 90.0, "mg/dL", "N", "<150", "2571-8", 0, (0.10, 0.48, 0.55, 0.52), "Triglycerides: 90 mg/dL"),
    ],
    # p02-whitaker-cbc.pdf
    "whitaker_cbc": [
        ("wbc", 7.2, "K/uL", "N", "4.5-11.0", "6690-2", 0, (0.10, 0.30, 0.55, 0.34), "WBC: 7.2 K/uL"),
        ("rbc", 4.5, "M/uL", "N", "4.2-5.4", "789-8", 0, (0.10, 0.36, 0.55, 0.40), "RBC: 4.5 M/uL"),
        ("hemoglobin", 13.8, "g/dL", "N", "12.0-16.0", "718-7", 0, (0.10, 0.42, 0.55, 0.46), "Hemoglobin: 13.8 g/dL"),
        ("hematocrit", 41.5, "%", "N", "37-47", "4544-3", 0, (0.10, 0.48, 0.55, 0.52), "Hematocrit: 41.5%"),
        ("platelets", 225.0, "K/uL", "N", "150-400", "777-3", 0, (0.10, 0.54, 0.55, 0.58), "Platelets: 225 K/uL"),
    ],
    # p03-reyes-hba1c — image, sparser extraction
    "reyes_hba1c": [
        ("hba1c", 8.2, "%", "H", "<7.0", "4548-4", 0, None, "HbA1c: 8.2%"),
        ("glucose_fasting", 162.0, "mg/dL", "H", "70-100", "1558-6", 0, None, "Fasting Glucose: 162 mg/dL"),
    ],
    # p04-kowalski-cmp.pdf
    "kowalski_cmp": [
        ("glucose", 95.0, "mg/dL", "N", "70-100", "2345-7", 0, (0.10, 0.28, 0.55, 0.32), "Glucose: 95 mg/dL"),
        ("bun", 18.0, "mg/dL", "N", "7-25", "3094-0", 0, (0.10, 0.34, 0.55, 0.38), "BUN: 18 mg/dL"),
        ("creatinine", 0.9, "mg/dL", "N", "0.6-1.2", "2160-0", 0, (0.10, 0.40, 0.55, 0.44), "Creatinine: 0.9 mg/dL"),
        ("sodium", 140.0, "mEq/L", "N", "136-145", "2947-0", 0, (0.10, 0.46, 0.55, 0.50), "Sodium: 140 mEq/L"),
        ("potassium", 4.1, "mEq/L", "N", "3.5-5.0", "2823-3", 0, (0.10, 0.52, 0.55, 0.56), "Potassium: 4.1 mEq/L"),
    ],
}

_INTAKE_FIXTURES: dict[str, list[tuple[str, object, int, str | None]]] = {
    # p01-chen-intake-typed.pdf  — shape: (name, value, page_index, quote)
    "chen_intake": [
        ("vitals.height", "5ft 6in", 0, "Height: 5ft 6in"),
        ("vitals.weight", "158 lbs", 0, "Weight: 158 lbs"),
        ("vitals.bp_systolic", 128, 0, "BP: 128/82"),
        ("vitals.bp_diastolic", 82, 0, "BP: 128/82"),
        ("chief_complaint", "Annual physical", 0, "Reason for visit: Annual physical"),
        ("smoking_status", "Never", 0, "Tobacco use: Never"),
        ("allergies.self_reported", "Penicillin - rash", 0, "Allergies: Penicillin - rash"),
    ],
    # p02-whitaker-intake.pdf
    "whitaker_intake": [
        ("vitals.height", "6ft 1in", 0, "Height: 6ft 1in"),
        ("vitals.weight", "195 lbs", 0, "Weight: 195 lbs"),
        ("chief_complaint", "Chest tightness on exertion", 0, "Chief complaint: Chest tightness on exertion"),
        ("smoking_status", "Former", 0, "Tobacco use: Former smoker, quit 2018"),
        ("medications.self_reported", "Atenolol 50 mg daily", 0, "Current medications: Atenolol 50 mg daily"),
    ],
    # p03-reyes-intake.png — handwritten, sparser
    "reyes_intake": [
        ("chief_complaint", "Fatigue and increased thirst", 0, None),
        ("vitals.weight", "220 lbs", 0, None),
        ("smoking_status", "Never", 0, None),
    ],
    # p04-kowalski-intake.png — dirty scan
    "kowalski_intake": [
        ("chief_complaint", "Follow-up diabetes management", 0, None),
        ("vitals.weight", "245 lbs", 0, None),
        ("vitals.bp_systolic", 138, 0, None),
        ("vitals.bp_diastolic", 88, 0, None),
    ],
}


def is_eval_mode() -> bool:
    return _EVAL_MODE


def get_lab_mock_fields(fixture_key: str) -> list[tuple[str, object, str | None, str | None, str | None, str | None, int, tuple[float, float, float, float] | None, str | None]]:
    """Return mock lab fields for a known fixture_key in eval mode.

    fixture_key is a short label like 'chen_lipid'. Returns empty list if
    the key is not found (extractor should then return empty fields, not raise).
    """
    return list(_LAB_FIXTURES.get(fixture_key, []))


def get_intake_mock_fields(fixture_key: str) -> list[tuple[str, object, int, str | None]]:
    """Return mock intake fields for a known fixture_key in eval mode."""
    return list(_INTAKE_FIXTURES.get(fixture_key, []))


def resolve_lab_fixture_key(document_sha256: str, filename: str = "") -> str:
    """Map a document sha256 or filename hint to a fixture key."""
    fn = filename.lower()
    if "chen" in fn and ("lipid" in fn or "lab" in fn):
        return "chen_lipid"
    if "whitaker" in fn and "cbc" in fn:
        return "whitaker_cbc"
    if "reyes" in fn and "hba1c" in fn:
        return "reyes_hba1c"
    if "kowalski" in fn and "cmp" in fn:
        return "kowalski_cmp"
    # Fallback: first 8 chars of sha are not in our table, return empty
    return document_sha256[:8]


def resolve_intake_fixture_key(document_sha256: str, filename: str = "") -> str:
    fn = filename.lower()
    if "chen" in fn and "intake" in fn:
        return "chen_intake"
    if "whitaker" in fn and "intake" in fn:
        return "whitaker_intake"
    if "reyes" in fn and "intake" in fn:
        return "reyes_intake"
    if "kowalski" in fn and "intake" in fn:
        return "kowalski_intake"
    return document_sha256[:8]
