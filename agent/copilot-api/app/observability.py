"""Langfuse instrumentation - PHI-safe metadata only."""

from __future__ import annotations

import os
from typing import Any

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


def record_brief(
    trace_id: str,
    use_case: str,
    patient_uuid_hash: str,
    packet_count: int,
    usage: dict[str, Any],
    verifier_status: str,
    unsupported_dropped: int,
    duration_ms: float,
) -> None:
    """Best-effort. A trace-sink outage never breaks the brief response."""

    client = _get_client()
    if client is None:
        return
    try:
        trace = client.trace(
            id=trace_id,
            name="clinical_copilot.brief",
            metadata={
                "use_case": use_case,
                "patient_uuid_hash": patient_uuid_hash,
                "packet_count": packet_count,
                "verifier_status": verifier_status,
                "unsupported_dropped": unsupported_dropped,
                "prompt_template_version": usage.get("prompt_template_version"),
                "model": usage.get("model"),
            },
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
            metadata={"duration_ms": duration_ms, "repair": usage.get("repair", False)},
        )
    except Exception:
        pass
