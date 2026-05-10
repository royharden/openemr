"""Integration tests for POST /v1/extract/intake-form (Wk2 Workstream A, §15.5)."""

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
_PATIENT_HASH = hashlib.sha256(b"patient-intake-int").hexdigest()
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

_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


class TestExtractIntakeFormEndpoint:
    def test_returns_200_with_pdf(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-intake-typed.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code == 200

    def test_doc_type_is_intake_form(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-intake-typed.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.json()["doc_type"] == "intake_form"

    def test_missing_secret_returns_4xx(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/intake-form",
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("form.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code in (403, 422)

    def test_png_intake_accepted(self, client: TestClient) -> None:
        """PNG images are valid for intake forms (scanned handwritten)."""
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p03-reyes-intake.png", io.BytesIO(_PNG_HEADER), "image/png")},
        )
        assert response.status_code == 200

    def test_oversized_file_returns_413(self, client: TestClient) -> None:
        large_content = b"%PDF-1.4\n" + b"x" * (8 * 1024 * 1024 + 1)
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("big.pdf", io.BytesIO(large_content), "application/pdf")},
        )
        assert response.status_code == 413

    def test_response_has_document_sha256(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        expected_sha = hashlib.sha256(pdf).hexdigest()
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-intake-typed.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.json()["document_sha256"] == expected_sha

    def test_whitaker_intake_has_field_count(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/intake-form",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p02-whitaker-intake.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["extracted_field_count"] > 0
