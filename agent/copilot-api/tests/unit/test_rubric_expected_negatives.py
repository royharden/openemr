"""L1: rubric floors count expected negative-control failures correctly."""

from __future__ import annotations

from evals.rubrics import rubric_citation_present
from evals.runner import _apply_expected_rubric_failures


def test_citation_present_passes_when_no_claims_but_missing_data_is_documented() -> None:
    assert rubric_citation_present(
        {},
        {
            "verified_response": {
                "claims": [],
                "missing_data": ["No guideline evidence found in the current corpus."],
                "refusals": [],
            }
        },
    )


def test_expected_rubric_failure_counts_as_case_pass_for_floor_math() -> None:
    case = {
        "expectations": {
            "expected_rubric_failures": ["citation_present"],
        }
    }

    adjusted, failures = _apply_expected_rubric_failures(
        case,
        {"schema_valid": True, "citation_present": False},
    )

    assert failures == []
    assert adjusted == {"schema_valid": True, "citation_present": True}


def test_expected_rubric_failure_fails_if_the_negative_control_stops_failing() -> None:
    case = {
        "expectations": {
            "expected_rubric_failures": ["citation_present"],
        }
    }

    adjusted, failures = _apply_expected_rubric_failures(
        case,
        {"schema_valid": True, "citation_present": True},
    )

    assert adjusted["citation_present"] is False
    assert failures == ["rubric/citation_present: expected FAIL but passed"]
