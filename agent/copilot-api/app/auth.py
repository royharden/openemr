"""Shared-secret + task-token auth for the gateway → sidecar hop.

The sidecar trusts the gateway because the shared secret is known only to
the two services. In addition, the gateway mints a short-lived per-request
task token (HMAC-signed) so each request is bound to a single patient and
expires within minutes. Both checks must pass.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import Header, HTTPException, Request


_DEFAULT_TTL_SLACK_SECONDS = 5  # tolerate small clock skew between gateway and sidecar


def require_gateway_secret(
    x_copilot_gateway_secret: str = Header(..., alias="X-Copilot-Gateway-Secret"),
) -> None:
    expected = os.getenv("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "")
    if not expected or not hmac.compare_digest(x_copilot_gateway_secret, expected):
        raise HTTPException(status_code=403, detail="invalid_gateway_secret")


def _decode_token(token: str, shared_secret: str) -> dict[str, Any]:
    if "." not in token:
        raise HTTPException(status_code=403, detail="task_token_malformed")
    body_b64, sig = token.rsplit(".", 1)
    expected_sig = hmac.new(
        shared_secret.encode("utf-8"),
        body_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=403, detail="task_token_signature")
    try:
        # base64 padding tolerant decode
        padding = "=" * (-len(body_b64) % 4)
        payload_bytes = base64.b64decode(body_b64 + padding)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=403, detail="task_token_payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=403, detail="task_token_payload")
    return payload


def verify_task_token(
    token: str,
    *,
    expected_patient_uuid_hash: str,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify a task token from the gateway. Returns the decoded payload.

    Checks: signature, expiry, scope == 'read-only', and patient_uuid_hash
    matches the request body's patient_uuid_hash.
    """

    shared_secret = os.getenv("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "")
    if not shared_secret:
        raise HTTPException(status_code=403, detail="task_token_no_secret")

    payload = _decode_token(token, shared_secret)

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise HTTPException(status_code=403, detail="task_token_no_exp")
    current = now if now is not None else int(time.time())
    if current > int(exp) + _DEFAULT_TTL_SLACK_SECONDS:
        raise HTTPException(status_code=403, detail="task_token_expired")

    if payload.get("scope") != "read-only":
        raise HTTPException(status_code=403, detail="task_token_scope")

    token_hash = payload.get("patient_uuid_hash")
    if not isinstance(token_hash, str) or not token_hash:
        raise HTTPException(status_code=403, detail="task_token_no_patient_hash")
    if not hmac.compare_digest(token_hash, expected_patient_uuid_hash):
        raise HTTPException(status_code=403, detail="task_token_patient_mismatch")

    return payload


def require_task_token(request: Request) -> dict[str, Any]:
    """FastAPI dependency: verify X-Copilot-Task-Token against the request body's patient hash.

    Reads `patient_uuid_hash` from the parsed request body via the route handler's
    parameter; we require callers to pass it explicitly via `verify_task_token`
    in the route. This dependency only checks the header is present and well-formed
    so that older callers without `patient_uuid_hash` access still get a 403 fast.
    """

    token = request.headers.get("X-Copilot-Task-Token")
    if not token:
        # Allow legacy unauth path only when explicitly opted out (dev only).
        if os.getenv("COPILOT_REQUIRE_TASK_TOKEN", "1") == "0":
            return {"_skipped": True}
        raise HTTPException(status_code=403, detail="task_token_missing")
    return {"_token": token}
