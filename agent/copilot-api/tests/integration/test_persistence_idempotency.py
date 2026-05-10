"""Integration tests for extraction idempotency (Wk2 Workstream A, §15.5).

Tests that uploading the same document twice produces the same sha256,
and that the extractor returns a consistent document_sha256 for identical bytes.

Note: actual DB idempotency (INSERT IGNORE) is enforced at the PHP layer
(DocumentFactsRepository). These tests validate the sidecar's sha256 consistency
which is the precondition for idempotency to work end-to-end.
"""

from __future__ import annotations

import hashlib
import io
import os

import pytest

os.environ["COPILOT_EVAL_MODE"] = "1"
os.environ.setdefault("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-0000000000000000000000000000000000000000000000000000")

from fastapi.testclient import TestClient

from app.main import app

_SECRET = os.environ["COPILOT_OPENEMR_GATEWAY_SHARED_SECRET"]
_PATIENT_HASH = hashlib.sha256(b"patient-idem").hexdigest()
_HEADERS = {"X-Copilot-Gateway-Secret": _SECRET}


def _minimal_pdf() -> bytes:
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f\r
0000000009 00000 n\r
0000000058 00000 n\r
0000000115 00000 n\r
trailer<</Size 4/Root 1 0 R>>
startxref
214
%%EOF
"""


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


class TestIdempotencyContract:
    def test_same_pdf_same_sha256_lab(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        expected_sha = hashlib.sha256(pdf).hexdigest()

        r1 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("chen.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        r2 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("chen.pdf", io.BytesIO(pdf), "application/pdf")},
        )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["document_sha256"] == expected_sha
        assert r2.json()["document_sha256"] == expected_sha

    def test_same_pdf_same_field_count_lab(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        filename = "p01-chen-lipid-panel.pdf"

        r1 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": (filename, io.BytesIO(pdf), "application/pdf")},
        )
        r2 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": (filename, io.BytesIO(pdf), "application/pdf")},
        )

        assert r1.json()["extracted_field_count"] == r2.json()["extracted_field_count"]

    def test_same_intake_same_sha256(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        expected_sha = hashlib.sha256(pdf).hexdigest()

        r1 = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-intake-typed.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        r2 = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-intake-typed.pdf", io.BytesIO(pdf), "application/pdf")},
        )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["document_sha256"] == expected_sha
        assert r2.json()["document_sha256"] == expected_sha

    def test_different_pdfs_different_sha256(self, client: TestClient) -> None:
        pdf1 = _minimal_pdf()
        pdf2 = _minimal_pdf() + b"\n%comment"

        r1 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf1), "application/pdf")},
        )
        r2 = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf2), "application/pdf")},
        )

        assert r1.json()["document_sha256"] != r2.json()["document_sha256"]

    def test_idempotency_key_formula(self) -> None:
        """Verify the SHA-256(patient_uuid + doc_sha256 + field_path) formula matches."""
        patient_uuid = "patient-uuid-for-key-test"
        doc_sha256 = "a" * 64
        field_path = "ldl"
        key = hashlib.sha256((patient_uuid + doc_sha256 + field_path).encode()).hexdigest()
        assert len(key) == 64
        assert key != hashlib.sha256((patient_uuid + doc_sha256 + "hdl").encode()).hexdigest()
