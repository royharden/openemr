"""Langfuse instrumentation - PHI-safe metadata only."""

from __future__ import annotations

import os
import re as _re
from typing import Any

# ---------------------------------------------------------------------------
# Canonical trace + span names emitted by this module.
#
# Plan_wk2_Claude_Next05 §5.3 (Codex finding #26): the original
# `agentdocs/latency_percentiles.py` was authored against
# `clinical_copilot.brief` trace names, but the production path now emits
# `clinical_copilot.graph` traces with `graph.<node>` spans (LangGraph
# supervisor + workers). Exporting the names as module-level constants
# lets external consumers (the latency script, future canary tools,
# unit tests) import the canonical strings instead of hardcoding them
# and silently drifting. Tests assert that `record_graph_span` / `record_brief`
# / `record_local_refusal` actually emit these names, so a future rename
# fails CI rather than the cost report.
# ---------------------------------------------------------------------------

GRAPH_TRACE_NAME = "clinical_copilot.graph"
GRAPH_SPAN_PREFIX = "graph."
BRIEF_TRACE_NAME = "clinical_copilot.brief"
LOCAL_REFUSAL_TRACE_NAME = "clinical_copilot.local_refusal"

# ---------------------------------------------------------------------------
# PHI scrubbing (AgDR-0055)
# ---------------------------------------------------------------------------

_PHI_PATTERNS = [
    _re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),               # SSN
    _re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                # ISO date
    _re.compile(r"\b\d{3}[.\-\s]\d{3}[.\-\s]\d{4}\b"),   # phone
    _re.compile(r"\bMRN[:\s]\s*\S+", _re.IGNORECASE),     # MRN
    _re.compile(r"\bpatient[_\s]?name[:\s]\s*\S+", _re.IGNORECASE),
]

# AgDR-0084 / Plan §3.7 — keys whose values are "filename-like" and whose
# values must be either redacted at source or scrubbed before emission.
# A future Langfuse span emitter that adds a new filename-like key should
# add the key here so the helper below can redact it without per-call
# inspection of the metadata dict.
_FILENAME_LIKE_KEYS = frozenset({
    "filename",
    "file_name",
    "original_filename",
    "raw_filename",
    "upload_filename",
})


def scrub_phi(text: str) -> str:
    """Replace PHI-like patterns with [REDACTED] before Langfuse emission."""
    for pattern in _PHI_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# Pre-redacted filename pattern emitted by ``copilot_upload_redact_filename``
# (PHP) and ``redact_filename`` (Python, ``app/routes.py``). Matches the
# whole string ``upload-{8 hex chars}.{1-8 lowercase-alnum chars}``.
_SAFE_REDACTED_FILENAME = _re.compile(r"^upload-[a-f0-9]{8}\.[a-z0-9]{1,8}$")


def strip_filename_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """AgDR-0084 / Plan §3.7 — defensively scrub filename-like keys from a
    metadata dict before it lands in Langfuse trace + span emission.

    The PHP gateway redacts uploaded filenames to ``"upload-{sha8}.{ext}"``
    at the boundary, so a well-behaved emission path already carries the
    safe form. This helper is the last line of defense: if a value at a
    filename-like key does NOT match the ``upload-{sha8}.{ext}`` shape,
    replace it wholesale with ``"[REDACTED-FILENAME]"`` rather than
    relying on regex pattern matching against arbitrary PHI shapes
    (``scrub_phi`` uses ``\\b`` word boundaries which silently miss ISO
    dates embedded in underscore-separated filenames). The replacement
    is intentionally information-free — if a future audit needs to
    correlate a redacted log line back to a document, the
    co-emitted ``document_sha256`` field is the right pivot.

    Returns a NEW dict (not mutated in place) so callers can safely pass
    the result to ``client.trace(metadata=...)`` without affecting the
    caller's local state.
    """
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in _FILENAME_LIKE_KEYS and isinstance(value, str):
            out[key] = value if _SAFE_REDACTED_FILENAME.match(value) else "[REDACTED-FILENAME]"
        elif isinstance(value, dict):
            out[key] = strip_filename_from_metadata(value)
        else:
            out[key] = value
    return out

try:
    from langfuse import Langfuse
    _LANGFUSE_AVAILABLE = True
except ImportError:
    Langfuse = None  # type: ignore[assignment,misc]
    _LANGFUSE_AVAILABLE = False


_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    if not _LANGFUSE_AVAILABLE:
        return None
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        _client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception:
        _client = None
    return _client


_VERDICT_TO_SCORE = {
    "helpful": 1.0,
    "missing_data": -0.5,
    "incorrect": -1.0,
    "too_slow": -0.25,
    "source_unclear": -0.5,
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def estimate_cost_usd(usage: dict[str, Any]) -> float:
    """Estimate LLM cost from token usage using configurable per-1M-token rates."""

    input_rate = _env_float("COPILOT_COST_INPUT_PER_1M", 1.00)
    output_rate = _env_float("COPILOT_COST_OUTPUT_PER_1M", 5.00)
    cache_read_rate = _env_float("COPILOT_COST_CACHE_READ_PER_1M", 0.10)
    cache_write_rate = _env_float("COPILOT_COST_CACHE_WRITE_PER_1M", 1.25)

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_read_tokens = usage.get("cache_read_input_tokens", 0) or 0
    cache_write_tokens = usage.get("cache_creation_input_tokens", 0) or 0

    return round(
        (
            input_tokens * input_rate
            + output_tokens * output_rate
            + cache_read_tokens * cache_read_rate
            + cache_write_tokens * cache_write_rate
        )
        / 1_000_000,
        6,
    )


def record_feedback(trace_id: str, verdict: str, comment: str) -> bool:
    """Forward clinician feedback to Langfuse as a score event. Best-effort."""

    client = _get_client()
    if client is None:
        return False
    try:
        client.score(
            trace_id=trace_id,
            name="clinician_feedback",
            value=_VERDICT_TO_SCORE.get(verdict, 0.0),
            comment=comment[:500] if comment else None,
            data_type="NUMERIC",
        )
        return True
    except Exception:
        return False


def record_local_refusal(
    trace_id: str,
    use_case: str,
    router_family: str,
    refusal_reason: str,
    patient_uuid_hash: str,
) -> bool:
    """Emit a Langfuse trace for a gateway-only refusal turn.

    The gateway never calls the LLM in this case (e.g. "should I increase
    the dose?"). We still emit a trace so observability covers all four
    turn outcomes: verified, repaired, refused-by-router, sidecar-failed.
    Cost is 0; no token usage; no PHI beyond the already-hashed patient.
    """

    client = _get_client()
    if client is None:
        return False
    try:
        client.trace(
            id=trace_id,
            name=LOCAL_REFUSAL_TRACE_NAME,
            metadata={
                "use_case": use_case,
                "router_family": router_family,
                "refusal_reason": refusal_reason,
                "patient_uuid_hash": patient_uuid_hash,
                "verifier_status": "refused_by_router",
                "estimated_cost_usd": 0.0,
            },
        )
        return True
    except Exception:
        return False


def record_brief(
    trace_id: str,
    use_case: str,
    patient_uuid_hash: str,
    packet_count: int,
    usage: dict[str, Any],
    verifier_status: str,
    unsupported_dropped: int,
    duration_ms: float,
    router_family: str | None = None,
    selected_tools: list[str] | None = None,
    planner_status: str | None = None,
    tool_results_summary: list[dict[str, Any]] | None = None,
) -> None:
    """Best-effort. A trace-sink outage never breaks the brief response."""

    client = _get_client()
    if client is None:
        return
    try:
        estimated_cost_usd = estimate_cost_usd(usage)
        metadata: dict[str, Any] = {
            "use_case": use_case,
            "patient_uuid_hash": patient_uuid_hash,
            "packet_count": packet_count,
            "verifier_status": verifier_status,
            "unsupported_dropped": unsupported_dropped,
            "prompt_template_version": usage.get("prompt_template_version"),
            "model": usage.get("model"),
            "estimated_cost_usd": estimated_cost_usd,
        }
        if router_family is not None:
            metadata["router_family"] = router_family
        if selected_tools is not None:
            metadata["selected_tools"] = selected_tools
        if planner_status is not None:
            metadata["planner_status"] = planner_status
        if tool_results_summary is not None:
            metadata["tool_results_summary"] = [
                {
                    "tool": str(item.get("tool", "")),
                    "packet_count": int(item.get("packet_count", 0) or 0),
                    "status": str(item.get("status", "")),
                }
                for item in tool_results_summary[:6]
                if isinstance(item, dict)
            ]
        trace = client.trace(
            id=trace_id,
            name=BRIEF_TRACE_NAME,
            metadata=metadata,
        )
        trace.generation(
            name="brief_v1",
            model=usage.get("model"),
            usage={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "input_cached_read": usage.get("cache_read_input_tokens", 0),
                "input_cache_write": usage.get("cache_creation_input_tokens", 0),
            },
            metadata={
                "duration_ms": duration_ms,
                "repair": usage.get("repair", False),
                "estimated_cost_usd": estimated_cost_usd,
            },
        )
    except Exception:
        pass


def record_graph_span(
    trace_id: str,
    node_name: str,
    graph_path: list[str],
    worker_handoffs: list[dict[str, Any]],
    decision_reason: str,
    duration_ms: float,
) -> None:
    """Emit a Langfuse span for a LangGraph node transition. PHI-scrubbed. Best-effort."""
    client = _get_client()
    if client is None:
        return
    try:
        safe_reason = scrub_phi(decision_reason)
        trace = client.trace(id=trace_id, name=GRAPH_TRACE_NAME)
        trace.span(
            name=f"{GRAPH_SPAN_PREFIX}{node_name}",
            metadata={
                "graph_path": graph_path,
                "worker_handoffs": worker_handoffs,
                "decision_reason": safe_reason,
                "duration_ms": duration_ms,
            },
        )
    except Exception:
        pass
