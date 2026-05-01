"""Pydantic schemas — single source of truth for request/response shapes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class BriefRequest(BaseModel):
    trace_id: str
    use_case: Literal["pre_room_brief", "what-changed"] = "pre_room_brief"
    patient_uuid_hash: str = Field(..., description="SHA256-truncated patient UUID")
    packets: list[SourcePacket]


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
