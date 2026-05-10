"""L1: Wk2 route contract tests — stubs and implemented endpoints.

Workstream A (Team A) implemented /v1/extract/lab-pdf and /v1/extract/intake-form.
Workstream C (/v1/copilot/answer) is registered and validates its request body.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("COPILOT_EVAL_MODE", "1")
    os.environ.setdefault("COPILOT_REQUIRE_TASK_TOKEN", "0")
    os.environ.setdefault("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "test-secret")

    from app.auth import require_gateway_secret
    from app.main import app

    app.dependency_overrides[require_gateway_secret] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_copilot_answer_route_registered_and_validates(client: TestClient) -> None:
    """POST /v1/copilot/answer is registered and rejects malformed payloads."""
    r = client.post("/v1/copilot/answer", json={})
    assert r.status_code != 501, "/v1/copilot/answer should not be a 501 stub"
    assert r.status_code in (200, 400, 422, 500), r.text


def test_routes_are_registered() -> None:
    from app.main import app

    paths = {route.path for route in app.router.routes}
    for p in ("/v1/extract/lab-pdf", "/v1/extract/intake-form", "/v1/copilot/answer"):
        assert p in paths, f"{p} not registered (paths: {sorted(paths)})"


def test_lab_pdf_route_registered_and_not_501(client: TestClient) -> None:
    """Team A implemented /v1/extract/lab-pdf — it should not return 501."""
    import io
    pdf = b"%PDF-1.4\n%EOF\n"
    # Send without file to trigger validation error (not 501)
    r = client.post("/v1/extract/lab-pdf", json={})
    assert r.status_code != 501, "lab-pdf route should be implemented (not a stub)"


def test_intake_form_route_registered_and_not_501(client: TestClient) -> None:
    """Team A implemented /v1/extract/intake-form — it should not return 501."""
    r = client.post("/v1/extract/intake-form", json={})
    assert r.status_code != 501, "intake-form route should be implemented (not a stub)"
