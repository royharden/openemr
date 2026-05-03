"""Sidecar task-token auth tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from app.auth import verify_task_token


SECRET = "test-shared-secret"
PATIENT_HASH = "abc123def456"


def _mint_token(payload: dict, secret: str = SECRET) -> str:
    body = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", SECRET)


def _good_payload(**overrides) -> dict:
    payload = {
        "patient_uuid_hash": PATIENT_HASH,
        "user_id": 17,
        "encounter_uuid": "enc-1",
        "scope": "read-only",
        "pou": "TREAT",
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
    }
    payload.update(overrides)
    return payload


def test_valid_token_accepted():
    token = _mint_token(_good_payload())
    decoded = verify_task_token(token, expected_patient_uuid_hash=PATIENT_HASH)
    assert decoded["patient_uuid_hash"] == PATIENT_HASH
    assert decoded["scope"] == "read-only"


def test_expired_token_rejected():
    payload = _good_payload(iat=int(time.time()) - 2000, exp=int(time.time()) - 1000)
    token = _mint_token(payload)
    with pytest.raises(HTTPException) as exc:
        verify_task_token(token, expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_expired"


def test_tampered_signature_rejected():
    token = _mint_token(_good_payload())
    body, sig = token.rsplit(".", 1)
    tampered = body + "." + ("0" * len(sig))
    with pytest.raises(HTTPException) as exc:
        verify_task_token(tampered, expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_signature"


def test_wrong_scope_rejected():
    token = _mint_token(_good_payload(scope="write"))
    with pytest.raises(HTTPException) as exc:
        verify_task_token(token, expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_scope"


def test_patient_hash_mismatch_rejected():
    token = _mint_token(_good_payload())
    with pytest.raises(HTTPException) as exc:
        verify_task_token(token, expected_patient_uuid_hash="different-hash")
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_patient_mismatch"


def test_malformed_token_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_task_token("not-a-token", expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403


def test_missing_secret_rejected(monkeypatch):
    monkeypatch.setenv("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "")
    token = _mint_token(_good_payload())
    with pytest.raises(HTTPException) as exc:
        verify_task_token(token, expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_no_secret"


def test_no_exp_field_rejected():
    payload = _good_payload()
    del payload["exp"]
    token = _mint_token(payload)
    with pytest.raises(HTTPException) as exc:
        verify_task_token(token, expected_patient_uuid_hash=PATIENT_HASH)
    assert exc.value.status_code == 403
    assert exc.value.detail == "task_token_no_exp"
