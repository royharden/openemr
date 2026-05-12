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


class _FakeV4Span:
    def __init__(self, name: str, metadata: dict[str, Any] | None = None) -> None:
        self.name = name
        self.metadata = metadata or {}
        self.children: list[_FakeV4Span] = []
        self.ended = False

    def update(self, **kwargs: Any) -> None:
        if "name" in kwargs:
            self.name = kwargs["name"]
        if "metadata" in kwargs:
            self.metadata = kwargs["metadata"]

    def start_observation(self, **kwargs: Any) -> "_FakeV4Span":
        child = _FakeV4Span(str(kwargs["name"]), kwargs.get("metadata"))
        self.children.append(child)
        return child

    def end(self) -> None:
        self.ended = True


class _FakeV4Langfuse:
    def __init__(self) -> None:
        self.roots: list[_FakeV4Span] = []
        self.flushed = False

    def create_trace_id(self, *, seed: str) -> str:
        assert seed == "trace-uuid-style"
        return "a" * 32

    def start_observation(self, **kwargs: Any) -> _FakeV4Span:
        root = _FakeV4Span(str(kwargs["name"]), kwargs.get("metadata"))
        self.roots.append(root)
        return root

    def flush(self) -> None:
        self.flushed = True


def test_record_graph_span_supports_langfuse_v4_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeV4Langfuse()
    monkeypatch.setattr(observability, "_get_client", lambda: client)
    monkeypatch.setenv("COPILOT_LANGFUSE_FLUSH_IMMEDIATE", "1")

    observability.record_graph_span(
        trace_id="trace-uuid-style",
        node_name="graph_complete",
        graph_path=["synthesizer", "verifier"],
        worker_handoffs=[],
        decision_reason="route completed",
        duration_ms=123.0,
    )

    assert len(client.roots) == 1
    root = client.roots[0]
    assert root.name == observability.GRAPH_TRACE_NAME
    assert root.metadata["gateway_trace_id"] == "trace-uuid-style"
    assert root.metadata["langfuse_trace_id"] == "a" * 32
    assert root.metadata["trace_name"] == observability.GRAPH_TRACE_NAME

    assert len(root.children) == 1
    child = root.children[0]
    assert child.name == "graph.graph_complete"
    assert child.metadata["span_name"] == "graph.graph_complete"
    assert child.metadata["duration_ms"] == 123.0
    assert child.ended is True
    assert root.ended is True
    assert client.flushed is True


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


def test_strip_filename_from_metadata_replaces_unsafe_value_wholesale() -> None:
    """Filename-like keys with anything other than the safe redacted form
    get replaced with ``[REDACTED-FILENAME]`` wholesale."""
    md = {
        "filename": "smith_anne_dob_1962-04-14_lipid.pdf",
        "trace_id": "trace-123",  # NOT filename-like — should pass through.
    }
    out = observability.strip_filename_from_metadata(md)
    # Every PHI token is gone because the WHOLE value is replaced.
    assert out["filename"] == "[REDACTED-FILENAME]"
    for phi in ("smith", "anne", "1962", "04-14", "lipid"):
        assert phi.lower() not in out["filename"].lower()
    # Non-filename keys pass through unchanged.
    assert out["trace_id"] == "trace-123"


def test_strip_filename_from_metadata_preserves_safe_redacted_form() -> None:
    """A value already in the gateway-redacted ``upload-{sha8}.{ext}`` form
    is preserved as-is so traceability via the SHA prefix still works."""
    md = {
        "filename": "upload-a1b2c3d4.pdf",
        "file_name": "upload-deadbeef.png",
        "original_filename": "upload-cafef00d.jpeg",
    }
    out = observability.strip_filename_from_metadata(md)
    assert out["filename"] == "upload-a1b2c3d4.pdf"
    assert out["file_name"] == "upload-deadbeef.png"
    assert out["original_filename"] == "upload-cafef00d.jpeg"


def test_strip_filename_from_metadata_recurses_into_nested_dicts() -> None:
    """Nested metadata dicts get recursed; filename keys at any depth scrub."""
    md = {
        "outer_key": "untouched",
        "nested": {
            "filename": "MRN: 8453 patient_name: Smith",
            "depth_2": {
                "original_filename": "file_2026-05-11.pdf",
            },
        },
    }
    out = observability.strip_filename_from_metadata(md)
    assert out["nested"]["filename"] == "[REDACTED-FILENAME]"
    assert out["nested"]["depth_2"]["original_filename"] == "[REDACTED-FILENAME]"
    assert out["outer_key"] == "untouched"


def test_strip_filename_from_metadata_returns_new_dict() -> None:
    """The helper does not mutate the caller's dict."""
    md = {"filename": "smith_anne_1962-04-14.pdf"}
    out = observability.strip_filename_from_metadata(md)
    # Caller's input is unchanged.
    assert md["filename"] == "smith_anne_1962-04-14.pdf"
    # Output is scrubbed.
    assert out["filename"] == "[REDACTED-FILENAME]"


def test_strip_filename_from_metadata_non_string_filename_passes_through() -> None:
    """A filename-like key with a non-string value (None, int, dict) is left alone."""
    md = {
        "filename": None,  # not a string
        "file_name": 42,    # not a string
    }
    out = observability.strip_filename_from_metadata(md)
    assert out == md


def test_strip_filename_from_metadata_covers_every_known_filename_key() -> None:
    """Locks the filename-like key allowlist. A future emitter that adds a
    new filename-like key MUST add it to ``_FILENAME_LIKE_KEYS`` AND to
    this test so the scrubber catches it.
    """
    expected = {"filename", "file_name", "original_filename", "raw_filename", "upload_filename"}
    assert observability._FILENAME_LIKE_KEYS == expected


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
