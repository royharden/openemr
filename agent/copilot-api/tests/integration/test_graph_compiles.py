"""Integration test: the LangGraph graph compiles without errors in eval mode."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def set_eval_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_EVAL_MODE", "1")
    # Clear Langfuse env so no external call is attempted
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)


def test_graph_compiles() -> None:
    """build_graph() must complete without ImportError or RuntimeError in eval mode."""
    try:
        from app.graph.build import build_graph
        graph = build_graph()
        assert graph is not None
    except (ImportError, RuntimeError) as e:
        if "langgraph" in str(e).lower():
            pytest.skip(f"langgraph not installed: {e}")
        raise


def test_get_compiled_graph_is_cached() -> None:
    """get_compiled_graph() must return the same object on repeated calls."""
    try:
        from app.graph.build import get_compiled_graph
        import app.graph.build as build_mod

        build_mod._compiled_graph = None  # reset cache
        g1 = get_compiled_graph()
        g2 = get_compiled_graph()
        assert g1 is g2
    except (ImportError, RuntimeError) as e:
        if "langgraph" in str(e).lower():
            pytest.skip(f"langgraph not installed: {e}")
        raise


def test_node_constants_defined() -> None:
    """All required node name constants must be importable from supervisor."""
    from app.graph.supervisor import (
        NODE_END,
        NODE_EVIDENCE_RETRIEVER,
        NODE_INTAKE_EXTRACTOR,
        NODE_SYNTHESIZER,
        NODE_VERIFIER,
    )
    assert all(isinstance(n, str) for n in [
        NODE_END, NODE_EVIDENCE_RETRIEVER, NODE_INTAKE_EXTRACTOR,
        NODE_SYNTHESIZER, NODE_VERIFIER,
    ])
