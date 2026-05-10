"""L1: Wk2 W0.5 route stubs are registered and return HTTP 501 (Workstream A/C take over their bodies)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Lifespan triggers app.startup_self_test(). Run in eval mode so the
    # vendor-credential ping is skipped.
    os.environ.setdefault("COPILOT_EVAL_MODE", "1")
    os.environ.setdefault("COPILOT_REQUIRE_TASK_TOKEN", "0")
    os.environ.setdefault("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "test-secret")

    from app.auth import require_gateway_secret
    from app.main import app

    # Bypass the gateway-secret check at the dependency layer — these stubs
    # are about route registration + 501, not auth (auth is exercised in its
    # own tests).
    app.dependency_overrides[require_gateway_secret] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path,expected_detail",
    [
        ("/v1/extract/lab-pdf", "not_implemented_workstream_a"),
        ("/v1/extract/intake-form", "not_implemented_workstream_a"),
        ("/v1/copilot/answer", "not_implemented_workstream_c"),
    ],
)
def test_stub_returns_501(client: TestClient, path: str, expected_detail: str) -> None:
    r = client.post(path, json={})
    assert r.status_code == 501, r.text
    assert r.json()["detail"] == expected_detail


def test_routes_are_registered() -> None:
    from app.main import app

    paths = {route.path for route in app.router.routes}
    for p in ("/v1/extract/lab-pdf", "/v1/extract/intake-form", "/v1/copilot/answer"):
        assert p in paths, f"{p} not registered (paths: {sorted(paths)})"
