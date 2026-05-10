"""Unit tests for app.observability.scrub_phi (AgDR-0055)."""

from __future__ import annotations

import pytest

from app.observability import scrub_phi


class TestScrubPhiSSN:
    def test_replaces_ssn(self) -> None:
        assert "123-45-6789" not in scrub_phi("SSN: 123-45-6789")

    def test_leaves_non_ssn_dashes_alone(self) -> None:
        result = scrub_phi("Order ID: 1234-5")
        assert "1234-5" in result


class TestScrubPhiISODate:
    def test_replaces_iso_date(self) -> None:
        result = scrub_phi("DOB: 1978-07-22")
        assert "1978-07-22" not in result

    def test_replaces_observed_at_date(self) -> None:
        text = "Observed at: 2026-04-01"
        result = scrub_phi(text)
        assert "2026-04-01" not in result


class TestScrubPhiPhone:
    def test_replaces_phone_dashes(self) -> None:
        result = scrub_phi("Call 555-867-5309")
        assert "555-867-5309" not in result

    def test_replaces_phone_dots(self) -> None:
        result = scrub_phi("555.867.5309")
        assert "555.867.5309" not in result


class TestScrubPhiMRN:
    def test_replaces_mrn_label(self) -> None:
        result = scrub_phi("MRN: 00012345")
        assert "00012345" not in result

    def test_case_insensitive_mrn(self) -> None:
        result = scrub_phi("mrn:ABC999")
        assert "ABC999" not in result


class TestScrubPhiPatientName:
    def test_replaces_patient_name(self) -> None:
        result = scrub_phi("patient_name: JohnDoe")
        assert "JohnDoe" not in result

    def test_case_insensitive_patient_name(self) -> None:
        result = scrub_phi("Patient Name: JaneDoe")
        assert "JaneDoe" not in result


class TestScrubPhiCombined:
    def test_multiple_phi_patterns_all_scrubbed(self) -> None:
        text = "SSN 123-45-6789 DOB 1980-01-15 MRN:XYZ001"
        result = scrub_phi(text)
        assert "123-45-6789" not in result
        assert "1980-01-15" not in result
        assert "XYZ001" not in result

    def test_empty_string_unchanged(self) -> None:
        assert scrub_phi("") == ""

    def test_no_phi_unchanged(self) -> None:
        text = "Sodium: 140 mEq/L — within normal range."
        result = scrub_phi(text)
        assert result == text
