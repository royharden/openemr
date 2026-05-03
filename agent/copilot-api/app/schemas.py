"""Pydantic schemas — single source of truth for request/response shapes."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SourcePacket(BaseModel):
    source_id: str
    patient_uuid: str
    resource_type: str
    source_table: str
    source_uuid: str | None = None
    field: str
    label: str
    value: Any = None
    unit: str | None = None
    observed_at: str | None = None
    last_updated: str | None = None
    freshness: Literal["recent", "stale", "unknown"] = "unknown"
    status: str | None = None
    sensitive: bool = False


UseCase = Literal[
    "pre_room_brief",
    "what-changed",
    "medication_check",
    "allergy_check",
    "recent_abnormal_labs",
    "immunization_history",
    "free_text_followup",
]

ClinicalToolName = Literal[
    "get_patient_identity",
    "get_active_problems",
    "get_active_medications",
    "get_allergy_list",
    "get_recent_labs",
    "get_immunization_history",
]

PlannerStatus = Literal["planned", "fallback_required", "failed"]


class ToolCall(BaseModel):
    name: ClinicalToolName
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def _reject_patient_or_query_args(cls, v: dict[str, Any]) -> dict[str, Any]:
        forbidden = {
            "pid",
            "patient_id",
            "patient_uuid",
            "patient_uuid_hash",
            "sql",
            "query",
            "table",
            "table_name",
            "source_id",
        }
        bad = forbidden.intersection(v.keys())
        if bad:
            raise ValueError(f"forbidden tool argument(s): {', '.join(sorted(bad))}")
        return v


class ToolPlanRequest(BaseModel):
    trace_id: str
    use_case: UseCase = "pre_room_brief"
    patient_uuid_hash: str = Field(..., description="SHA256-truncated patient UUID")
    question: str | None = Field(None, max_length=500)
    router_family: str | None = Field(None, max_length=64)

    @field_validator("question")
    @classmethod
    def _no_control_chars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _CONTROL_CHAR_RE.search(v):
            raise ValueError("question contains control characters")
        return v


class ToolPlanResponse(BaseModel):
    trace_id: str
    planner_status: PlannerStatus
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=6)
    usage: dict[str, Any] = Field(default_factory=dict)


class BriefRequest(BaseModel):
    trace_id: str
    use_case: UseCase = "pre_room_brief"
    patient_uuid_hash: str = Field(..., description="SHA256-truncated patient UUID")
    packets: list[SourcePacket]
    question: str | None = Field(
        None,
        max_length=500,
        description="Free-text question for the free_text_followup use case. Gateway "
        "must normalize and strip control chars before sending.",
    )
    prior_turn_source_ids: list[str] | None = Field(
        None,
        max_length=20,
        description="Verified source_ids from the prior turn (display-only context, IDs only).",
    )
    router_family: str | None = Field(
        None,
        max_length=64,
        description="Gateway-classified family for free-text questions, used as observability metadata.",
    )
    selected_tools: list[ClinicalToolName] | None = Field(
        None,
        max_length=6,
        description="Gateway-executed tool names selected by the sidecar planner or fallback map.",
    )
    planner_status: PlannerStatus | None = Field(
        None,
        description="How the gateway obtained the selected tool list.",
    )
    tool_results_summary: list[dict[str, Any]] | None = Field(
        None,
        max_length=6,
        description="PHI-minimized per-tool packet counts and execution status.",
    )

    @field_validator("question")
    @classmethod
    def _no_control_chars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _CONTROL_CHAR_RE.search(v):
            raise ValueError("question contains control characters")
        return v


class Claim(BaseModel):
    text: str = Field(..., description="Rendered to physician verbatim. Plain text only.")
    claim_type: Literal["fact", "trend", "absence", "conflict"]
    source_ids: list[str] = Field(
        ...,
        description="Each ID MUST exist in the request packet set. Empty list = unsupported.",
    )
    caveat: str | None = None


class LLMOutput(BaseModel):
    answer_type: Literal["pre_room_brief", "follow_up", "refusal"]
    claims: list[Claim] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    refusals: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    trace_id: str
    verdict: Literal[
        "helpful",
        "missing_data",
        "incorrect",
        "too_slow",
        "source_unclear",
    ]
    comment: str = ""


class FeedbackAck(BaseModel):
    trace_id: str
    verdict: str
    recorded: bool


class LocalRefusalRequest(BaseModel):
    trace_id: str
    use_case: str = Field(..., max_length=64)
    router_family: str = Field(..., max_length=64)
    refusal_reason: str = Field(..., max_length=128)
    patient_uuid_hash: str = Field(..., max_length=64)


class LocalRefusalAck(BaseModel):
    trace_id: str
    recorded: bool


class VerifierIssue(BaseModel):
    rule: str
    claim_index: int | None = None
    detail: str


class VerifiedResponse(BaseModel):
    answer_type: str
    claims: list[Claim]
    missing_data: list[str]
    refusals: list[str]
    suggested_followups: list[str]
    verifier_status: Literal["passed", "passed_with_drops", "failed"]
    unsupported_dropped: int = 0
    verifier_issues: list[VerifierIssue] = Field(default_factory=list)
    trace_id: str
    selected_tools: list[ClinicalToolName] = Field(default_factory=list)
    planner_status: PlannerStatus | None = None
    tool_results_summary: list[dict[str, Any]] = Field(default_factory=list)
