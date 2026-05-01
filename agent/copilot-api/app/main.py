"""FastAPI sidecar entrypoint."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .auth import require_gateway_secret
from .observability import record_feedback
from .orchestrator import process_brief
from .schemas import BriefRequest, FeedbackAck, FeedbackRequest, VerifiedResponse

app = FastAPI(title="Clinical Co-Pilot Sidecar", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/brief", response_model=VerifiedResponse, dependencies=[Depends(require_gateway_secret)])
def post_brief(req: BriefRequest) -> VerifiedResponse:
    return process_brief(req)


@app.post("/v1/feedback", response_model=FeedbackAck, dependencies=[Depends(require_gateway_secret)])
def post_feedback(req: FeedbackRequest) -> FeedbackAck:
    recorded = record_feedback(req.trace_id, req.verdict, req.comment)
    return FeedbackAck(trace_id=req.trace_id, verdict=req.verdict, recorded=recorded)
