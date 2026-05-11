"""L1: observability trace+span name alignment (Plan §5.3, Codex finding #26).

Verifies that ``app/observability.py`` exports the canonical Langfuse
trace + span names as module-level constants AND uses those constants
inside its own ``record_*`` functions. The cost report (gitignored
``agentdocs/latency_percentiles.py``) and any future canary tool import
these constants directly rather than hardcoding strings, so a future
rename of the trace/span names is caught by this test instead of by a
silently-empty cost report.

What this catches:
  * A future agent that renames ``GRAPH_TRACE_NAME`` but leaves a stale
    string literal inside ``record_graph_span`` -- the trace would emit
    under the new name but the legacy span path would emit under the old
    name, splitting the data points across two Langfuse projects and
    making p95 numbers nonsensical.
  * A future agent that adds a NEW trace name (e.g. ``clinical_copilot.critic``
    for the Phase 6.1 critic worker) but forgets to export it -- the
    cost report misses the new node entirely.

Test strategy: monkey-patch ``Langfuse`` via the module's lazy client
factory, capture all ``client.trace(name=...)`` and ``client.trace(...).span(name=...)``
calls, then assert the names match the exported constants.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app import observability


def test_canonical_trace_names_are_exported() -> None:
    """The four canonical names must be module-level string constants."""
    assert isinstance(observability.GRAPH_TRACE_NAME, str)
    assert isinstance(observability.GRAPH_SPAN_PREFIX, str)
    assert isinstance(observability.BRIEF_TRACE_NAME, str)
    assert isinstance(observability.LOCAL_REFUSAL_TRACE_NAME, str)
    assert observability.GRAPH_TRACE_NAME == "clinical_copilot.graph"
    assert observability.GRAPH_SPAN_PREFIX == "graph."
    assert observability.BRIEF_TRACE_NAME == "clinical_copilot.brief"
    assert observability.LOCAL_REFUSAL_TRACE_NAME == "clinical_copilot.local_refusal"


@pytest.fixture()
def captured_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Yield a mock Langfuse client that captures every trace/span call.

    The fixture patches ``observability._get_client`` so the module's
    ``record_*`` functions exercise the mock instead of skipping when
    no real Langfuse credentials are configured.
    """
    client = MagicMock()
    trace = MagicMock()
    client.trace.return_value = trace
    monkeypatch.setattr(observability, "_get_client", lambda: client)
    # Also reset the module-level client cache so a previous test's mock
    # does not bleed into this one.
    monkeypatch.setattr(observability, "_client", None)
    return client


def test_record_graph_span_uses_graph_trace_name(captured_client: MagicMock) -> None:
    observability.record_graph_span(
        trace_id="trace-123",
        node_name="supervisor",
        graph_path=["intake", "supervisor"],
        worker_handoffs=[],
        decision_reason="route to evidence_retriever",
        duration_ms=42.0,
    )
    captured_client.trace.assert_called_once()
    _, kwargs = captured_client.trace.call_args
    assert kwargs.get("id") == "trace-123"
    assert kwargs.get("name") == observability.GRAPH_TRACE_NAME

    trace = captured_client.trace.return_value
    trace.span.assert_called_once()
    _, span_kwargs = trace.span.call_args
    assert span_kwargs.get("name", "").startswith(observability.GRAPH_SPAN_PREFIX)
    assert span_kwargs.get("name") == "graph.supervisor"


def test_record_local_refusal_uses_local_refusal_trace_name(
    captured_client: MagicMock,
) -> None:
    ok = observability.record_local_refusal(
        trace_id="trace-456",
        use_case="dose_change",
        router_family="prescriptive",
        refusal_reason="out_of_scope",
        patient_uuid_hash="hash-abc",
    )
    assert ok is True
    captured_client.trace.assert_called_once()
    _, kwargs = captured_client.trace.call_args
    assert kwargs.get("name") == observability.LOCAL_REFUSAL_TRACE_NAME


def test_record_brief_uses_brief_trace_name(captured_client: MagicMock) -> None:
    usage: dict[str, Any] = {
        "input_tokens": 100,
        "output_tokens": 50,
        "model": "claude-haiku-4-5-20251001",
    }
    observability.record_brief(
        trace_id="trace-789",
        use_case="brief",
        patient_uuid_hash="hash-xyz",
        packet_count=4,
        usage=usage,
        verifier_status="verified",
        unsupported_dropped=0,
        duration_ms=850.0,
    )
    captured_client.trace.assert_called_once()
    _, kwargs = captured_client.trace.call_args
    assert kwargs.get("name") == observability.BRIEF_TRACE_NAME


def test_no_stale_string_literals_in_record_functions() -> None:
    """Belt-and-suspenders: scan observability.py source for stale literal
    occurrences of the canonical strings outside the constant definitions.

    Any hit means a future refactor introduced a divergence between the
    constants and an actual emission site. This catches the
    "renamed-the-constant-but-not-the-call-site" failure mode.
    """
    import inspect

    source = inspect.getsource(observability)
    # The constants definition block legitimately mentions every name; the
    # record_* functions should reference them via identifier, not via
    # literal string. We assert each canonical name appears EXACTLY ONCE
    # as a quoted string (in the constants block).
    for canonical in (
        observability.GRAPH_TRACE_NAME,
        observability.BRIEF_TRACE_NAME,
        observability.LOCAL_REFUSAL_TRACE_NAME,
    ):
        quoted_double = f'"{canonical}"'
        quoted_single = f"'{canonical}'"
        count = source.count(quoted_double) + source.count(quoted_single)
        assert count == 1, (
            f"Expected exactly one quoted literal for {canonical!r} in "
            f"observability.py (the constant definition); found {count}. "
            "A record_* function likely hardcodes the string instead of "
            "referencing the constant -- fix it to use the constant by "
            "name so future renames stay aligned."
        )
