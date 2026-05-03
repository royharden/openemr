"""LLM tool-planning for gateway-executed clinical data tools."""

from __future__ import annotations

import os
from typing import Any

from .llm import _client, _usage_dict
from .schemas import ToolCall, ToolPlanRequest, ToolPlanResponse

_TOOL_PLAN_NAME = "emit_tool_plan"

_TOOL_DESCRIPTIONS = [
    {
        "name": "get_patient_identity",
        "description": "Current patient's demographics and chart identity summary. No arguments.",
        "arguments": {},
    },
    {
        "name": "get_active_problems",
        "description": "Current patient's active problem list. No arguments.",
        "arguments": {},
    },
    {
        "name": "get_active_medications",
        "description": "Current patient's active medication list and prescriptions. No arguments.",
        "arguments": {},
    },
    {
        "name": "get_allergy_list",
        "description": "Current patient's allergy list and recorded reactions. No arguments.",
        "arguments": {},
    },
    {
        "name": "get_recent_labs",
        "description": "Recent lab results. Optional arguments: months integer 1-24, limit integer 1-20.",
        "arguments": {"months": "integer 1-24", "limit": "integer 1-20"},
    },
    {
        "name": "get_immunization_history",
        "description": "Current patient's immunization history. No arguments.",
        "arguments": {},
    },
]


def fallback_tool_calls(use_case: str, router_family: str | None = None) -> list[ToolCall]:
    """Deterministic minimum map used only when the planner returns no usable tools."""

    key = router_family or use_case
    tool_names = {
        "medication_check": ["get_patient_identity", "get_active_medications", "get_allergy_list"],
        "medication": ["get_patient_identity", "get_active_medications", "get_allergy_list"],
        "allergy_check": ["get_patient_identity", "get_allergy_list", "get_active_medications"],
        "allergy": ["get_patient_identity", "get_allergy_list", "get_active_medications"],
        "recent_abnormal_labs": ["get_patient_identity", "get_active_problems", "get_recent_labs"],
        "labs": ["get_patient_identity", "get_active_problems", "get_recent_labs"],
        "immunization_history": ["get_patient_identity", "get_immunization_history"],
        "immunization": ["get_patient_identity", "get_immunization_history"],
        "identity": ["get_patient_identity"],
        "what_changed": [
            "get_patient_identity",
            "get_active_problems",
            "get_active_medications",
            "get_allergy_list",
            "get_recent_labs",
            "get_immunization_history",
        ],
        "what-changed": [
            "get_patient_identity",
            "get_active_problems",
            "get_active_medications",
            "get_allergy_list",
            "get_recent_labs",
            "get_immunization_history",
        ],
    }.get(
        key,
        [
            "get_patient_identity",
            "get_active_problems",
            "get_active_medications",
            "get_allergy_list",
            "get_recent_labs",
            "get_immunization_history",
        ],
    )
    return [ToolCall(name=name, arguments={}) for name in tool_names]


def _planner_tool() -> dict[str, Any]:
    return {
        "name": _TOOL_PLAN_NAME,
        "description": "Choose the read-only OpenEMR tools needed to answer the current-patient request.",
        "input_schema": ToolPlanResponse.model_json_schema(),
    }


def _planner_prompt(req: ToolPlanRequest) -> str:
    return (
        "You are planning read-only clinical data tool calls for an OpenEMR gateway.\n"
        "The gateway, not you, executes tools for the already-authenticated current patient.\n"
        "Return only tool calls from the allowlist. Do not include pid, patient_uuid, SQL, table names, "
        "source IDs, or arbitrary query text in arguments. If a question asks about another patient or "
        "clinical action, return no tools with planner_status='failed'; the gateway router should already "
        "have refused these.\n\n"
        f"Allowed tools: {_TOOL_DESCRIPTIONS}\n\n"
        "Request metadata, PHI-minimized:\n"
        f"trace_id={req.trace_id}\n"
        f"use_case={req.use_case}\n"
        f"patient_uuid_hash={req.patient_uuid_hash}\n"
        f"router_family={req.router_family or ''}\n"
        f"question={req.question or ''}\n"
    )


def call_tool_plan(req: ToolPlanRequest) -> ToolPlanResponse:
    """Call the LLM planner. Exceptions are converted to planner_status='failed'."""

    try:
        response = _client().messages.create(
            model=os.getenv("COPILOT_TOOL_PLANNER_MODEL", os.getenv("COPILOT_MODEL", "claude-haiku-4-5-20251001")),
            max_tokens=1024,
            system="Select only the minimum read-only current-patient data tools needed.",
            tools=[_planner_tool()],
            tool_choice={"type": "tool", "name": _TOOL_PLAN_NAME},
            messages=[{"role": "user", "content": _planner_prompt(req)}],
        )
    except Exception:
        return ToolPlanResponse(trace_id=req.trace_id, planner_status="failed", tool_calls=[])

    tool_input: dict[str, Any] | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_PLAN_NAME:
            tool_input = block.input  # type: ignore[assignment]
            break

    usage = _usage_dict(response)
    usage["planner"] = True

    if tool_input is None:
        return ToolPlanResponse(trace_id=req.trace_id, planner_status="failed", tool_calls=[], usage=usage)

    try:
        parsed = ToolPlanResponse.model_validate(tool_input)
    except Exception:
        return ToolPlanResponse(trace_id=req.trace_id, planner_status="failed", tool_calls=[], usage=usage)

    usable = [call for call in parsed.tool_calls if isinstance(call, ToolCall)]
    if not usable:
        return ToolPlanResponse(trace_id=req.trace_id, planner_status="fallback_required", tool_calls=[], usage=usage)

    return ToolPlanResponse(
        trace_id=req.trace_id,
        planner_status="planned",
        tool_calls=usable[:6],
        usage=usage,
    )
