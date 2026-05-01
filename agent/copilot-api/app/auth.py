"""Shared-secret auth for the gateway → sidecar hop."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def require_gateway_secret(
    x_copilot_gateway_secret: str = Header(..., alias="X-Copilot-Gateway-Secret"),
) -> None:
    expected = os.getenv("COPILOT_OPENEMR_GATEWAY_SHARED_SECRET", "")
    if not expected or x_copilot_gateway_secret != expected:
        raise HTTPException(status_code=403, detail="invalid_gateway_secret")
