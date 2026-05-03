"""Anthropic SDK wrapper. Forces JSON via tool-use; parses with Pydantic."""

from __future__ import annotations

import os
import pathlib

import anthropic
from dotenv import load_dotenv

from .schemas import BriefRequest, LLMOutput

load_dotenv(override=False)
# An empty (but defined) ANTHROPIC_API_KEY in the parent shell would otherwise
# block dotenv from setting the real key. Treat empty as unset.
if not os.environ.get("ANTHROPIC_API_KEY"):
    load_dotenv(override=True)

_PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"
_BRIEF_V1 = (_PROMPTS_DIR / "brief_v1.txt").read_text(encoding="utf-8")

_MODEL = os.getenv("COPILOT_MODEL", "claude-haiku-4-5-20251001")
_PROMPT_TEMPLATE_VERSION = "v1"
_TOOL_NAME = "emit_briefing"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _briefing_tool() -> dict:
    schema = LLMOutput.model_json_schema()
    return {
        "name": _TOOL_NAME,
        "description": "Emit the structured pre-room briefing. Every claim must cite source_ids that exist in the request packets.",
        "input_schema": schema,
    }


def _user_payload(req: BriefRequest) -> dict:
    payload: dict = {
        "use_case": req.use_case,
        "patient_uuid_hash": req.patient_uuid_hash,
        "trace_id": req.trace_id,
        "packets": [p.model_dump(mode="json") for p in req.packets[:50]],
    }
    if req.question is not None:
        payload["question"] = req.question
    if req.prior_turn_source_ids:
        payload["prior_turn_source_ids"] = req.prior_turn_source_ids[:20]
    if req.router_family:
        payload["router_family"] = req.router_family
    if req.selected_tools:
        payload["selected_tools"] = req.selected_tools
    if req.planner_status:
        payload["planner_status"] = req.planner_status
    if req.tool_results_summary:
        payload["tool_results_summary"] = req.tool_results_summary
    return payload


def _parse_tool_use(response: anthropic.types.Message) -> tuple[LLMOutput | None, str]:
    raw_text = ""
    tool_input: dict | None = None
    for block in response.content:
        if block.type == "text":
            raw_text += block.text
        elif block.type == "tool_use" and block.name == _TOOL_NAME:
            tool_input = block.input  # type: ignore[assignment]
    if tool_input is None:
        return None, raw_text
    try:
        return LLMOutput.model_validate(tool_input), raw_text
    except Exception:
        return None, raw_text


def _usage_dict(response: anthropic.types.Message, *, repair: bool = False) -> dict:
    return {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        "model": _MODEL,
        "prompt_template_version": _PROMPT_TEMPLATE_VERSION,
        "repair": repair,
    }


def call_brief(req: BriefRequest) -> tuple[LLMOutput | None, dict, str]:
    """Returns (parsed_output, usage_dict, raw_text). parsed_output is None on parse failure."""

    client = _client()
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=_BRIEF_V1,
        tools=[_briefing_tool()],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    "Produce the briefing JSON for the following request via the "
                    f"{_TOOL_NAME} tool. Cite only the source_ids you see below.\n\n"
                    f"REQUEST: {_user_payload(req)}"
                ),
            }
        ],
    )
    parsed, raw_text = _parse_tool_use(response)
    return parsed, _usage_dict(response), raw_text


def call_brief_repair(req: BriefRequest, prior_errors: list[str], prior_raw: str) -> tuple[LLMOutput | None, dict]:
    """One repair pass: send the verifier errors back and ask Claude to fix the JSON."""

    client = _client()
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=_BRIEF_V1,
        tools=[_briefing_tool()],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    "Your previous response failed verification. Errors:\n- "
                    + "\n- ".join(prior_errors)
                    + f"\n\nReturn a corrected briefing via the {_TOOL_NAME} tool. "
                    "Drop unsupported claims rather than fabricating sources.\n\n"
                    f"REQUEST: {_user_payload(req)}"
                ),
            }
        ],
    )
    parsed, _ = _parse_tool_use(response)
    return parsed, _usage_dict(response, repair=True)
