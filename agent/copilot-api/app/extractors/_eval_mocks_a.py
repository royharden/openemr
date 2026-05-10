"""Deterministic eval-mode fixtures for Workstream A extractors.

When COPILOT_EVAL_MODE=1 this module supplies pre-built field lists so tests
never call the Anthropic Vision API.  Fixture keys are matched by filename
substring so multiple test files can reuse the same fixture without SHA-256
coordination.

FIXTURE KEY RESOLUTION ORDER (first match wins):
  1. Exact document_sha256 match in _SHA_OVERRIDES
  2. Filename substring match (longest match wins)
  3. Fall through → empty field list

MOCK_VERSION — bump when fixture data changes to bust stale cache.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

MOCK_VERSION = "wk2-a-v1"

_EVAL_MODE = os.environ.get("COPILOT_EVAL_MODE", "0") == "1"


def is_eval_mode() -> bool:
    return _EVAL_MODE


# ---------------------------------------------------------------------------
# Lab PDF fixtures
# ---------------------------------------------------------------------------

_LAB_FIXTURES: dict[str, list[dict[str, Any]]] = {
    "chen-lipid": [
        {"name": "total_cholesterol", "value": 198.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "Total Cholesterol: 198 mg/dL", "page_index": 0, "confidence": 0.97},
        {"name": "ldl", "value": 122.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "LDL: 122 mg/dL", "page_index": 0, "confidence": 0.97},
        {"name": "hdl", "value": 58.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "HDL: 58 mg/dL", "page_index": 0, "confidence": 0.97},
        {"name": "triglycerides", "value": 95.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "Triglycerides: 95 mg/dL", "page_index": 0, "confidence": 0.96},
    ],
    "whitaker-cbc": [
        {"name": "wbc", "value": 6.8, "unit": "K/uL", "abnormal": False, "quote_or_value": "WBC: 6.8 K/uL", "page_index": 0, "confidence": 0.96},
        {"name": "rbc", "value": 4.5, "unit": "M/uL", "abnormal": False, "quote_or_value": "RBC: 4.5 M/uL", "page_index": 0, "confidence": 0.96},
        {"name": "hemoglobin", "value": 13.8, "unit": "g/dL", "abnormal": False, "quote_or_value": "Hemoglobin: 13.8 g/dL", "page_index": 0, "confidence": 0.96},
        {"name": "hematocrit", "value": 41.2, "unit": "%", "abnormal": False, "quote_or_value": "Hematocrit: 41.2%", "page_index": 0, "confidence": 0.95},
        {"name": "platelets", "value": 245.0, "unit": "K/uL", "abnormal": False, "quote_or_value": "Platelets: 245 K/uL", "page_index": 0, "confidence": 0.96},
    ],
    "reyes-hba1c": [
        {"name": "hba1c", "value": 8.2, "unit": "%", "abnormal": True, "quote_or_value": "HbA1c: 8.2% H", "page_index": 0, "confidence": 0.88},
    ],
    "kowalski-cmp": [
        {"name": "sodium", "value": 140.0, "unit": "mEq/L", "abnormal": False, "quote_or_value": "Sodium: 140 mEq/L", "page_index": 0, "confidence": 0.82},
        {"name": "potassium", "value": 4.1, "unit": "mEq/L", "abnormal": False, "quote_or_value": "Potassium: 4.1 mEq/L", "page_index": 0, "confidence": 0.82},
        {"name": "creatinine", "value": 0.9, "unit": "mg/dL", "abnormal": False, "quote_or_value": "Creatinine: 0.9 mg/dL", "page_index": 0, "confidence": 0.80},
        {"name": "bun", "value": 18.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "BUN: 18 mg/dL", "page_index": 0, "confidence": 0.81},
        {"name": "glucose", "value": 95.0, "unit": "mg/dL", "abnormal": False, "quote_or_value": "Glucose: 95 mg/dL", "page_index": 0, "confidence": 0.80},
    ],
}

_LAB_FILENAME_MAP: list[tuple[str, str]] = [
    ("chen-lipid", "chen-lipid"),
    ("p01-chen-lipid", "chen-lipid"),
    ("p01-chen", "chen-lipid"),
    ("whitaker-cbc", "whitaker-cbc"),
    ("p02-whitaker", "whitaker-cbc"),
    ("reyes-hba1c", "reyes-hba1c"),
    ("p05-reyes", "reyes-hba1c"),
    ("kowalski-cmp", "kowalski-cmp"),
    ("p04-kowalski", "kowalski-cmp"),
]


def resolve_lab_fixture_key(document_sha256: str, filename: str) -> str | None:
    fn = filename.lower()
    best: tuple[int, str] | None = None
    for substr, key in _LAB_FILENAME_MAP:
        if substr.lower() in fn:
            length = len(substr)
            if best is None or length > best[0]:
                best = (length, key)
    return best[1] if best else None


def get_lab_mock_fields(fixture_key: str | None) -> list[dict[str, Any]]:
    if fixture_key is None:
        return []
    return list(_LAB_FIXTURES.get(fixture_key, []))


# ---------------------------------------------------------------------------
# Intake form fixtures
# ---------------------------------------------------------------------------

_INTAKE_FIXTURES: dict[str, list[dict[str, Any]]] = {
    "chen-intake": [
        {"name": "chief_complaint", "value": "Annual physical exam", "quote_or_value": "Annual physical exam", "page_index": 0, "confidence": 0.95, "bbox": None},
        {"name": "vitals.blood_pressure", "value": "118/76", "quote_or_value": "BP: 118/76 mmHg", "page_index": 0, "confidence": 0.96, "bbox": None},
        {"name": "vitals.heart_rate", "value": 72, "quote_or_value": "HR: 72 bpm", "page_index": 0, "confidence": 0.96, "bbox": None},
        {"name": "vitals.weight", "value": "142 lbs", "quote_or_value": "Weight: 142 lbs", "page_index": 0, "confidence": 0.95, "bbox": None},
        {"name": "medications.self_reported", "value": "Metformin 500mg twice daily", "quote_or_value": "Metformin 500mg BID", "page_index": 0, "confidence": 0.94, "bbox": None},
    ],
    "whitaker-intake": [
        {"name": "chief_complaint", "value": "Follow-up for hypertension", "quote_or_value": "Follow-up for hypertension", "page_index": 0, "confidence": 0.94, "bbox": None},
        {"name": "social_history.smoking_status", "value": "Former smoker", "quote_or_value": "Former smoker — quit 2018", "page_index": 0, "confidence": 0.93, "bbox": None},
        {"name": "vitals.blood_pressure", "value": "148/92", "quote_or_value": "BP: 148/92 mmHg", "page_index": 0, "confidence": 0.95, "bbox": None},
        {"name": "allergies.self_reported", "value": "Penicillin — rash", "quote_or_value": "Penicillin — rash", "page_index": 0, "confidence": 0.94, "bbox": None},
    ],
    "reyes-intake": [
        {"name": "chief_complaint", "value": "Diabetes management", "quote_or_value": None, "page_index": 0, "confidence": 0.72, "bbox": None},
        {"name": "vitals.blood_pressure", "value": "132/84", "quote_or_value": None, "page_index": 0, "confidence": 0.70, "bbox": None},
    ],
    "kowalski-intake": [
        {"name": "chief_complaint", "value": "Annual physical", "quote_or_value": None, "page_index": 0, "confidence": 0.75, "bbox": None},
        {"name": "vitals.blood_pressure", "value": "138/88", "quote_or_value": None, "page_index": 0, "confidence": 0.73, "bbox": None},
        {"name": "vitals.weight", "value": "245 lbs", "quote_or_value": None, "page_index": 0, "confidence": 0.72, "bbox": None},
    ],
}

_INTAKE_FILENAME_MAP: list[tuple[str, str]] = [
    ("chen-intake", "chen-intake"),
    ("p01-chen-intake", "chen-intake"),
    ("whitaker-intake", "whitaker-intake"),
    ("p02-whitaker-intake", "whitaker-intake"),
    ("reyes-intake", "reyes-intake"),
    ("p03-reyes-intake", "reyes-intake"),
    ("p03-reyes", "reyes-intake"),
    ("kowalski-intake", "kowalski-intake"),
    ("p04-kowalski-intake", "kowalski-intake"),
]


def resolve_intake_fixture_key(document_sha256: str, filename: str) -> str | None:
    fn = filename.lower()
    best: tuple[int, str] | None = None
    for substr, key in _INTAKE_FILENAME_MAP:
        if substr.lower() in fn:
            length = len(substr)
            if best is None or length > best[0]:
                best = (length, key)
    return best[1] if best else None


def get_intake_mock_fields(fixture_key: str | None) -> list[dict[str, Any]]:
    if fixture_key is None:
        return []
    fields: list[dict[str, Any]] = []
    for field in _INTAKE_FIXTURES.get(fixture_key, []):
        next_field = dict(field)
        if fixture_key == "whitaker-intake" and next_field.get("name") == "social_history.smoking_status":
            next_field["name"] = "smoking_status"
        if fixture_key == "kowalski-intake" and next_field.get("name") == "vitals.blood_pressure":
            fields.append({**next_field, "name": "vitals.bp_systolic", "value": 138})
            fields.append({**next_field, "name": "vitals.bp_diastolic", "value": 88})
            continue
        fields.append(next_field)
    return fields
