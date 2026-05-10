"""L1: evals/case_schema.json validates Wk1 cases unchanged AND locks Wk2 case shape."""

from __future__ import annotations

import json
import pathlib

import pytest

SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "evals" / "case_schema.json"
)
WK1_CASES_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "evals" / "cases"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema):
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(schema)


def test_schema_file_present() -> None:
    assert SCHEMA_PATH.exists(), f"missing {SCHEMA_PATH}"


def test_every_wk1_case_validates(validator) -> None:
    failures: list[str] = []
    for case_file in sorted(WK1_CASES_DIR.glob("*.json")):
        raw = json.loads(case_file.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(raw))
        if errors:
            failures.append(f"{case_file.name}: {errors[0].message}")
    assert not failures, "Wk1 cases must validate against the unified schema:\n" + "\n".join(failures)


def test_wk2_case_minimum_shape_validates(validator) -> None:
    case = {
        "case_id": "27_chen_lipid_citation_required",
        "category": "citation",
        "rubrics": ["schema_valid", "citation_present"],
        "expectations": {"verifier_status": "passed"},
        "what_bug_this_catches": "If extractor regresses to omitting source_id.",
    }
    errors = list(validator.iter_errors(case))
    assert not errors, [e.message for e in errors]


def test_wk2_case_missing_what_bug_this_catches_is_rejected(validator) -> None:
    case = {
        "case_id": "bad_case_no_explanation",
        "category": "extraction",
        "rubrics": ["schema_valid"],
        "expectations": {},
        # what_bug_this_catches missing
    }
    errors = list(validator.iter_errors(case))
    assert any("what_bug_this_catches" in e.message for e in errors), [e.message for e in errors]


def test_unknown_category_rejected(validator) -> None:
    case = {
        "case_id": "x",
        "category": "made_up",
        "rubrics": ["schema_valid"],
        "expectations": {},
        "what_bug_this_catches": "abc",
    }
    errors = list(validator.iter_errors(case))
    assert errors


def test_unknown_rubric_rejected(validator) -> None:
    case = {
        "case_id": "x",
        "category": "extraction",
        "rubrics": ["sweetness"],
        "expectations": {},
        "what_bug_this_catches": "abc",
    }
    errors = list(validator.iter_errors(case))
    assert errors


def test_case_without_name_or_case_id_rejected(validator) -> None:
    case = {"description": "anonymous"}
    errors = list(validator.iter_errors(case))
    assert errors
