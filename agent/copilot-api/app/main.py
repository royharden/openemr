"""FastAPI sidecar entrypoint."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .auth import require_gateway_secret
from .orchestrator import process_brief
from .schemas import BriefRequest, VerifiedResponse

app = FastAPI(title="Clinical Co-Pilot Sidecar", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/brief", response_model=VerifiedResponse, dependencies=[Depends(require_gateway_secret)])
def post_brief(req: BriefRequest) -> VerifiedResponse:
    return process_brief(req)
