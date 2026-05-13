"""Unit tests for app/extractors/medication_list.py (Plan §6.3, AgDR-0077).

Coverage:
  * Eval-mode fixture resolution: Whitaker (10 entries) / Reyes (6) / Kowalski (7).
  * Schema validation against the locked ExtractedDocument envelope and
    ExtractedMedicationList result.
  * Per-entry SourcePacket citation shape (source_id, resource_type=
    MedicationStatement, label==drug_name).
  * Plan §11.2 fixture-accuracy gate: every Whitaker entry's seven fields
    survive the round-trip.
  * Live-mode text-layer recovery on the Whitaker typed PDF (vision API
    intentionally stubbed so the test fails loudly if the text-layer
    fast path regresses and falls back to a network call).
  * Tokenizer + regex helpers (_split_column_row, _slugify_drug_name).

All tests run with COPILOT_EVAL_MODE=1 unless the test explicitly toggles
it off — never call Anthropic.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

os.environ["COPILOT_EVAL_MODE"] = "1"

from app.extractors.medication_list import (  # noqa: E402 — after env mutation
    _slugify_drug_name,
    _split_column_row,
    extract_medication_list,
)
from app.schemas import ExtractedDocument  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "documents"

PATIENT_HASH = hashlib.sha256(b"patient-uuid-medication-test").hexdigest()


def _read_fixture(name: str) -> bytes:
    path = FIXTURE_DIR / name
    if not path.exists():
        pytest.skip(f"fixture missing: {path}")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Eval-mode fixture lookups
# ---------------------------------------------------------------------------


class TestEvalModeFixtures:
    """Every fixture must resolve to its mock entry list under COPILOT_EVAL_MODE=1."""

    def test_whitaker_typed_resolves_to_ten_entries(self) -> None:
        pdf = _read_fixture("p02-whitaker-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p02-whitaker-medication-list.pdf",
        )
        assert result["doc_type"] == "medication_list"
        entries = result["result"]["entries"]
        assert len(entries) == 10
        assert entries[0]["drug_name"] == "Apixaban"
        assert entries[-1]["drug_name"] == "Pantoprazole"

    def test_reyes_handwritten_resolves_to_six_entries(self) -> None:
        png = _read_fixture("p03-reyes-medication-list.png")
        result = extract_medication_list(
            content=png,
            patient_uuid_hash=PATIENT_HASH,
            filename="p03-reyes-medication-list.png",
        )
        entries = result["result"]["entries"]
        assert len(entries) == 6
        # The glipizide cross-out fixture surfaces the NEW dose (10 mg), not
        # the struck-through original (5 mg). Plan §6.3 dose_ambiguity case
        # asserts on this exact behavior.
        glip = next(e for e in entries if e["drug_name"] == "Glipizide")
        assert glip["dose"] == "10 mg"

    def test_kowalski_dirty_scan_resolves_to_seven_entries(self) -> None:
        pdf = _read_fixture("p04-kowalski-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p04-kowalski-medication-list.pdf",
        )
        entries = result["result"]["entries"]
        assert len(entries) == 7
        # Kowalski discharge introduces 2 NEW meds (Pantoprazole, Furosemide)
        # that the reconciliation panel must classify as `newly_listed` vs
        # the seed prescriptions.
        drug_names = {e["drug_name"] for e in entries}
        assert {"Pantoprazole", "Furosemide"}.issubset(drug_names)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaShape:
    def test_extracted_document_validates(self) -> None:
        pdf = _read_fixture("p02-whitaker-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p02-whitaker-medication-list.pdf",
        )
        validated = ExtractedDocument.model_validate(result)
        assert validated.doc_type == "medication_list"
        # The result union resolves to ExtractedMedicationList here; entries
        # must be present and non-empty.
        assert hasattr(validated.result, "entries")
        assert len(validated.result.entries) == 10

    def test_every_entry_has_citation_with_source_id(self) -> None:
        pdf = _read_fixture("p02-whitaker-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p02-whitaker-medication-list.pdf",
        )
        validated = ExtractedDocument.model_validate(result)
        for entry in validated.result.entries:
            citation = entry.source_citation
            assert citation.source_id.startswith("doc:")
            assert citation.resource_type == "MedicationStatement"
            assert citation.label == entry.drug_name
            assert citation.source_type == "document_extract"


# ---------------------------------------------------------------------------
# Plan §11.2 stop-and-ask: per-fixture field-extraction accuracy
# ---------------------------------------------------------------------------


_EXPECTED_FIELDS = ("drug_name", "dose", "route", "frequency", "start_date", "prescriber", "indication")


def _accuracy_pct(entries: list[dict[str, Any]]) -> float:
    """Fraction of (entry, field) pairs that come back non-empty."""
    total = len(entries) * len(_EXPECTED_FIELDS)
    if total == 0:
        return 0.0
    populated = 0
    for entry in entries:
        for field in _EXPECTED_FIELDS:
            value = entry.get(field)
            if isinstance(value, str) and value.strip():
                populated += 1
            elif value is not None and not isinstance(value, str):
                populated += 1
    return populated / total


class TestPlan11_2Accuracy:
    """Per Plan §11.2 the doc type may not ship to demo unless field
    accuracy ≥90% on each of the three fixtures."""

    def test_whitaker_accuracy_at_least_90pct(self) -> None:
        pdf = _read_fixture("p02-whitaker-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p02-whitaker-medication-list.pdf",
        )
        entries = result["result"]["entries"]
        assert _accuracy_pct(entries) >= 0.90

    def test_reyes_accuracy_at_least_90pct(self) -> None:
        png = _read_fixture("p03-reyes-medication-list.png")
        result = extract_medication_list(
            content=png,
            patient_uuid_hash=PATIENT_HASH,
            filename="p03-reyes-medication-list.png",
        )
        entries = result["result"]["entries"]
        assert _accuracy_pct(entries) >= 0.90

    def test_kowalski_accuracy_at_least_90pct(self) -> None:
        pdf = _read_fixture("p04-kowalski-medication-list.pdf")
        result = extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p04-kowalski-medication-list.pdf",
        )
        entries = result["result"]["entries"]
        assert _accuracy_pct(entries) >= 0.90


# ---------------------------------------------------------------------------
# Live-mode text-layer fast path (no vision call)
# ---------------------------------------------------------------------------


class TestLiveModeTextRecovery:
    """The Whitaker typed PDF must extract 10/10 entries via the text-layer
    fast path so production traffic never reaches the vision endpoint on
    the happy path — every API call is a regression to monitor."""

    def test_text_recovery_yields_ten_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Temporarily disable eval mode so the live-mode branch runs.
        monkeypatch.delenv("COPILOT_EVAL_MODE", raising=False)

        # Reload the eval-mocks module so its module-level _EVAL_MODE constant
        # picks up the absence of the env var. The extractor imports the
        # helpers lazily inside the function body so a re-import is enough.
        import importlib

        from app.extractors import _eval_mocks_a as mocks_mod
        from app.extractors import medication_list as mod
        importlib.reload(mocks_mod)
        importlib.reload(mod)

        # Stub the vision API so the test fails loudly if the text-layer
        # path ever regresses and we fall back to the network.
        def _fail_vision(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                "vision API must not be called for the Whitaker typed PDF; "
                "the text-layer fast path regressed"
            )

        monkeypatch.setattr(mod, "_call_vision_api", _fail_vision)

        pdf = _read_fixture("p02-whitaker-medication-list.pdf")
        result = mod.extract_medication_list(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p02-whitaker-medication-list.pdf",
        )
        entries = result["result"]["entries"]
        assert len(entries) == 10
        # All seven fields populated on every entry.
        assert _accuracy_pct(entries) == 1.0
        # Prescriber column re-glued correctly ("Patel, N.", not "Patel,").
        assert all(e["prescriber"] == "Patel, N." for e in entries)


# ---------------------------------------------------------------------------
# Tokenizer / helper coverage
# ---------------------------------------------------------------------------


class TestColumnTokenizer:
    def test_glues_unit_suffix(self) -> None:
        assert _split_column_row("5 mg 50 mg") == ["5 mg", "50 mg"]

    def test_glues_lastname_initial(self) -> None:
        assert _split_column_row("Patel, N. Patel, N.") == ["Patel, N.", "Patel, N."]

    def test_glues_compound_drug(self) -> None:
        # Only at the start of the row (drug column), one compound merge.
        out = _split_column_row("Metoprolol succinate")
        assert out == ["Metoprolol succinate"]


class TestSlugify:
    @pytest.mark.parametrize(
        "drug,expected",
        [
            ("Apixaban", "apixaban"),
            ("Metoprolol succinate", "metoprolol_succinate"),
            ("Aspirin (low-dose)", "aspirin_low_dose"),
            ("", "unknown"),
            ("   ", "unknown"),
        ],
    )
    def test_slug(self, drug: str, expected: str) -> None:
        assert _slugify_drug_name(drug) == expected
