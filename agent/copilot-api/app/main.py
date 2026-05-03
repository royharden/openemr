"""FastAPI sidecar entrypoint."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header

from .auth import require_gateway_secret, verify_task_token
from .observability import record_feedback, record_local_refusal
from .orchestrator import process_brief
from .tool_planner import call_tool_plan
from .schemas import (
    BriefRequest,
    FeedbackAck,
    FeedbackRequest,
    LocalRefusalRequest,
    LocalRefusalAck,
    ToolPlanRequest,
    ToolPlanResponse,
    VerifiedResponse,
)

app = FastAPI(title="Clinical Co-Pilot Sidecar", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/brief", response_model=VerifiedResponse, dependencies=[Depends(require_gateway_secret)])
def post_brief(
    req: BriefRequest,
    x_copilot_task_token: str | None = Header(None, alias="X-Copilot-Task-Token"),
) -> VerifiedResponse:
    import os

    require_token = os.getenv("COPILOT_REQUIRE_TASK_TOKEN", "1") != "0"
    if require_token or x_copilot_task_token:
        if not x_copilot_task_token:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="task_token_missing")
        verify_task_token(
            x_copilot_task_token,
            expected_patient_uuid_hash=req.patient_uuid_hash,
        )
    return process_brief(req)


@app.post("/v1/tool-plan", response_model=ToolPlanResponse, dependencies=[Depends(require_gateway_secret)])
def post_tool_plan(req: ToolPlanRequest) -> ToolPlanResponse:
    return call_tool_plan(req)


@app.post("/v1/feedback", response_model=FeedbackAck, dependencies=[Depends(require_gateway_secret)])
def post_feedback(req: FeedbackRequest) -> FeedbackAck:
    recorded = record_feedback(req.trace_id, req.verdict, req.comment)
    return FeedbackAck(trace_id=req.trace_id, verdict=req.verdict, recorded=recorded)


@app.post(
    "/v1/trace/local_refusal",
    response_model=LocalRefusalAck,
    dependencies=[Depends(require_gateway_secret)],
)
def post_local_refusal(req: LocalRefusalRequest) -> LocalRefusalAck:
    """Record a gateway-only refusal turn so observability covers all turn outcomes.

    PHI must already be hashed/redacted before the gateway calls this.
    """

    recorded = record_local_refusal(
        trace_id=req.trace_id,
        use_case=req.use_case,
        router_family=req.router_family,
        refusal_reason=req.refusal_reason,
        patient_uuid_hash=req.patient_uuid_hash,
    )
    return LocalRefusalAck(trace_id=req.trace_id, recorded=recorded)
