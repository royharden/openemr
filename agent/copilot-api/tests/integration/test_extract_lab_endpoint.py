"""Integration tests for POST /v1/extract/lab-pdf (Wk2 Workstream A, §15.5).

Uses FastAPI TestClient. COPILOT_EVAL_MODE=1 so no Anthropic calls.
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
_PATIENT_UUID = "patient-uuid-integration"
_PATIENT_HASH = hashlib.sha256(_PATIENT_UUID.encode()).hexdigest()

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


class TestExtractLabPdfEndpoint:
    def test_returns_200_with_valid_pdf(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code == 200

    def test_response_has_doc_type_lab_pdf(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        body = response.json()
        assert body["doc_type"] == "lab_pdf"

    def test_response_has_document_sha256(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        expected_sha = hashlib.sha256(pdf).hexdigest()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        body = response.json()
        assert body["document_sha256"] == expected_sha

    def test_missing_gateway_secret_returns_4xx(self, client: TestClient) -> None:
        # FastAPI returns 422 (unprocessable) for a missing required header
        # when the route uses Form + File (body is parsed first). Either 403 or
        # 422 is acceptable; 200 is not.
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("test.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code in (403, 422)

    def test_wrong_secret_returns_403(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers={"X-Copilot-Gateway-Secret": "wrong-secret"},
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("test.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code == 403

    def test_oversized_file_returns_413(self, client: TestClient) -> None:
        large_content = b"%PDF-1.4\n" + b"x" * (8 * 1024 * 1024 + 1)
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("big.pdf", io.BytesIO(large_content), "application/pdf")},
        )
        assert response.status_code == 413

    def test_kowalski_fixture_extracts_creatinine(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p04-kowalski-cmp.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert response.status_code == 200
        fields = {f["name"]: f for f in response.json()["result"]["fields"]}
        assert "creatinine" in fields

    def test_extracted_field_count_matches_fields(self, client: TestClient) -> None:
        pdf = _minimal_pdf()
        response = client.post(
            "/v1/extract/lab-pdf",
            headers=_HEADERS,
            data={"patient_uuid_hash": _PATIENT_HASH},
            files={"file": ("p01-chen-lipid-panel.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        body = response.json()
        assert body["extracted_field_count"] == len(body["result"]["fields"])
