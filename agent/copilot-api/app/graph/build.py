"""Assemble and compile the CopilotState LangGraph StateGraph.

Wires supervisor routing functions as conditional edges.
Langfuse callback handler is attached at compile time when available.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_graph() -> Any:
    """Build and compile the LangGraph StateGraph. Returns a compiled graph."""
    try:
        from langgraph.graph import StateGraph, END  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "langgraph not installed. Run: pip install langgraph"
        ) from e

    from .nodes import (
        intake_extractor_node,
        evidence_retriever_node,
        synthesizer_node,
        verifier_node,
    )
    from .supervisor import (
        NODE_END,
        NODE_EVIDENCE_RETRIEVER,
        NODE_INTAKE_EXTRACTOR,
        NODE_SYNTHESIZER,
        NODE_VERIFIER,
        route_from_intake,
        route_from_retriever,
        route_from_start,
        route_from_synthesizer,
        route_from_verifier,
    )
    from .state import CopilotState

    graph = StateGraph(CopilotState)

    # Add nodes
    graph.add_node(NODE_INTAKE_EXTRACTOR, intake_extractor_node)
    graph.add_node(NODE_EVIDENCE_RETRIEVER, evidence_retriever_node)
    graph.add_node(NODE_SYNTHESIZER, synthesizer_node)
    graph.add_node(NODE_VERIFIER, verifier_node)

    # Entry: conditional from START
    graph.set_conditional_entry_point(
        route_from_start,
        {
            NODE_INTAKE_EXTRACTOR: NODE_INTAKE_EXTRACTOR,
            NODE_EVIDENCE_RETRIEVER: NODE_EVIDENCE_RETRIEVER,
        },
    )

    # Conditional edges from each node
    graph.add_conditional_edges(
        NODE_INTAKE_EXTRACTOR,
        route_from_intake,
        {NODE_EVIDENCE_RETRIEVER: NODE_EVIDENCE_RETRIEVER},
    )
    graph.add_conditional_edges(
        NODE_EVIDENCE_RETRIEVER,
        route_from_retriever,
        {NODE_SYNTHESIZER: NODE_SYNTHESIZER},
    )
    graph.add_conditional_edges(
        NODE_SYNTHESIZER,
        route_from_synthesizer,
        {NODE_VERIFIER: NODE_VERIFIER},
    )
    graph.add_conditional_edges(
        NODE_VERIFIER,
        route_from_verifier,
        {NODE_END: END},
    )

    # Attach Langfuse callback if available
    compile_kwargs: dict[str, Any] = {}
    langfuse_handler = _get_langfuse_handler()
    if langfuse_handler is not None:
        compile_kwargs["callbacks"] = [langfuse_handler]

    compiled = graph.compile(**compile_kwargs)
    logger.info("CopilotState graph compiled successfully")
    return compiled


def _get_langfuse_handler() -> Any:
    """Return a Langfuse CallbackHandler if credentials are configured."""
    if os.getenv("COPILOT_EVAL_MODE") == "1":
        return None
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse.callback import CallbackHandler  # type: ignore[import-not-found]
        return CallbackHandler(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com"),
        )
    except ImportError:
        logger.info("langfuse not installed; skipping Langfuse callback")
        return None
    except Exception as e:
        logger.warning("Langfuse callback setup failed: %s", e)
        return None


# Module-level compiled graph (lazy init)
_compiled_graph: Any = None


def get_compiled_graph() -> Any:
    """Return the cached compiled graph, building it on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
