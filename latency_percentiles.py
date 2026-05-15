"""Pull recent Langfuse traces and compute p50/p95 latency + cost.

Plan §9 / Wk2 cost-analysis augmentation (AgDR-pending). PHI-safe: this
script reads only trace/span metadata (durations, names, estimated cost) —
it never reads packet inputs/outputs.

Usage (from openemr/agent/copilot-api/ with the project venv active so the
``langfuse`` SDK is importable, or from any cwd if the SDK is on the host
Python path):

    LANGFUSE_PUBLIC_KEY=... \\
    LANGFUSE_SECRET_KEY=... \\
    LANGFUSE_HOST=https://us.cloud.langfuse.com \\
    python agentdocs/latency_percentiles.py [--n 50]

Output is a self-contained markdown block intended to be pasted directly
into ``agentdocs/cost_analysis_Wk2.md`` under the
``## Latency Profile (real Langfuse data)`` section.

Exits non-zero with a clear stderr message if credentials are missing or
the Langfuse API call fails.

References
----------
- ``agent/copilot-api/app/observability.py`` — trace/span emission. Trace
  names observed: ``clinical_copilot.brief``, ``clinical_copilot.graph``,
  ``clinical_copilot.local_refusal``. Per-node spans are emitted under
  ``clinical_copilot.graph`` with span names ``graph.<node>``.
- Langfuse Python SDK >=3.0 (project pin: ``langfuse>=3.0`` in
  ``agent/copilot-api/pyproject.toml``; tested against 4.5.1).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_OPENEMR_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_ROOT = _OPENEMR_ROOT / "agent" / "copilot-api"
if str(_SIDECAR_ROOT) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_ROOT))

try:
    from app.observability import BRIEF_TRACE_NAME, GRAPH_SPAN_PREFIX, GRAPH_TRACE_NAME
except ImportError:
    # Keep the script usable even if it is copied away from the repo, but the
    # in-repo path imports these from the emitter to prevent trace-name drift.
    GRAPH_TRACE_NAME = "clinical_copilot.graph"
    GRAPH_SPAN_PREFIX = "graph."
    BRIEF_TRACE_NAME = "clinical_copilot.brief"

# Default trace name to sample. The graph trace owns the node spans that this
# script reports; the legacy brief trace is still available via --trace-name.
DEFAULT_TRACE_NAME = GRAPH_TRACE_NAME

# LangGraph node names we expect to find as ``graph.<name>`` spans. Sourced
# from ``app/graph/supervisor.py`` constants.
EXPECTED_NODES = (
    "intake_extractor",
    "evidence_retriever",
    "synthesizer",
    "verifier",
)


def _die(msg: str, code: int = 2) -> None:
    print(f"latency_percentiles.py: error: {msg}", file=sys.stderr)
    sys.exit(code)


def _require_env() -> tuple[str, str, str]:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    if not public_key or not secret_key:
        _die(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in the "
            "environment. Source openemr/agent/copilot-api/.env (or the "
            "Docker-compose secret) before running."
        )
    return public_key, secret_key, host  # type: ignore[return-value]


def _percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolated percentile. ``pct`` in [0, 100]. ``None`` if empty."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


@dataclass
class NodeStats:
    durations_ms: list[float] = field(default_factory=list)

    def p50(self) -> float | None:
        return _percentile(self.durations_ms, 50.0)

    def p95(self) -> float | None:
        return _percentile(self.durations_ms, 95.0)

    def n(self) -> int:
        return len(self.durations_ms)


def _extract_duration_ms(obs: Any) -> float | None:
    """Best-effort extraction of an observation's duration in milliseconds.

    Langfuse observations expose ``startTime``/``endTime``. The SDK returns
    these as ``datetime`` objects on the response model. We also honor a
    ``duration_ms`` metadata field if the emitter recorded one (the
    ``record_graph_span`` helper does this).
    """
    # 1. metadata.duration_ms (preferred — emitted explicitly by record_graph_span)
    md = getattr(obs, "metadata", None) or {}
    if isinstance(md, dict):
        dur = md.get("duration_ms")
        if isinstance(dur, (int, float)) and dur >= 0:
            return float(dur)
    # 2. derive from start/end timestamps
    start = getattr(obs, "start_time", None) or getattr(obs, "startTime", None)
    end = getattr(obs, "end_time", None) or getattr(obs, "endTime", None)
    if start is not None and end is not None:
        try:
            return (end - start).total_seconds() * 1000.0
        except Exception:
            return None
    return None


def _extract_cost_usd(trace: Any) -> float:
    """Pull estimated_cost_usd off trace metadata. Returns 0.0 if absent."""
    md = getattr(trace, "metadata", None) or {}
    if isinstance(md, dict):
        c = md.get("estimated_cost_usd")
        if isinstance(c, (int, float)):
            return float(c)
    # Fall back to top-level totalCost if Langfuse computed it
    total = getattr(trace, "total_cost", None) or getattr(trace, "totalCost", None)
    if isinstance(total, (int, float)):
        return float(total)
    return 0.0


def _trace_duration_ms(trace: Any) -> float | None:
    """End-to-end latency for a trace, in milliseconds."""
    # Langfuse trace objects expose a ``latency`` (seconds) field on the
    # detailed view; the list endpoint may not include it. Fall back to
    # timestamp deltas where available.
    lat = getattr(trace, "latency", None)
    if isinstance(lat, (int, float)) and lat >= 0:
        return lat * 1000.0
    start = getattr(trace, "timestamp", None) or getattr(trace, "createdAt", None)
    end = getattr(trace, "updated_at", None) or getattr(trace, "updatedAt", None)
    if start is not None and end is not None:
        try:
            return (end - start).total_seconds() * 1000.0
        except Exception:
            return None
    return None


def collect(n: int, trace_name: str) -> tuple[dict[str, NodeStats], list[float], list[float]]:
    """Fetch the most recent ``n`` traces matching ``trace_name`` and aggregate.

    Returns (node_stats_by_name, end_to_end_ms, costs_usd).
    """
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        _die(
            "langfuse SDK not installed in this Python environment. Run "
            "from openemr/agent/copilot-api/ with the project venv "
            "activated, or `pip install 'langfuse>=3.0'`."
        )

    public_key, secret_key, host = _require_env()
    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)  # type: ignore[name-defined]

    try:
        traces_resp = client.api.trace.list(name=trace_name, limit=n, order_by="timestamp.desc")
    except Exception as e:
        _die(f"Langfuse trace.list failed: {e!r}")

    traces = getattr(traces_resp, "data", None) or []
    if not traces:
        _die(
            f"No traces named {trace_name!r} found in Langfuse. Run the "
            "Docker stack and exercise the brief endpoint (or the eval "
            "harness with LANGFUSE_* set) before re-running."
        )

    node_stats: dict[str, NodeStats] = {name: NodeStats() for name in EXPECTED_NODES}
    end_to_end_ms: list[float] = []
    costs_usd: list[float] = []

    for tr in traces:
        e2e = _trace_duration_ms(tr)
        costs_usd.append(_extract_cost_usd(tr))

        trace_id = getattr(tr, "id", None)
        if not trace_id:
            continue
        # Pull per-node spans for this trace. The graph emitter writes a
        # sibling trace named "clinical_copilot.graph" — we query by
        # span-name prefix and join across both trace IDs implicitly.
        try:
            obs_resp = client.api.observations.get_many(
                trace_id=trace_id,
                limit=50,
                fields="name,metadata,latency",
                expand_metadata="true",
            )
        except Exception:
            continue
        for obs in getattr(obs_resp, "data", None) or []:
            metadata = getattr(obs, "metadata", None) or {}
            span_name = getattr(obs, "name", "") or ""
            if not span_name and isinstance(metadata, dict):
                span_name = str(metadata.get("span_name") or "")
            if not span_name.startswith(GRAPH_SPAN_PREFIX):
                if trace_name == BRIEF_TRACE_NAME and span_name == "brief_v1":
                    dur = _extract_duration_ms(obs)
                    if dur is not None:
                        e2e = dur
                continue
            node = span_name[len(GRAPH_SPAN_PREFIX):]
            if node not in node_stats:
                continue
            dur = _extract_duration_ms(obs)
            if dur is not None:
                node_stats[node].durations_ms.append(dur)

        if e2e is not None:
            end_to_end_ms.append(e2e)

    try:
        client.shutdown()
    except Exception:
        pass

    return node_stats, end_to_end_ms, costs_usd


def self_test(n: int = 5) -> int:
    """Print recent trace/span names so operators can confirm alignment."""

    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        _die(
            "langfuse SDK not installed in this Python environment. Run "
            "from openemr/agent/copilot-api/ with the project venv "
            "activated, or `pip install 'langfuse>=3.0'`."
        )

    public_key, secret_key, host = _require_env()
    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)  # type: ignore[name-defined]

    try:
        traces_resp = client.api.trace.list(limit=n, order_by="timestamp.desc")
    except Exception as e:
        _die(f"Langfuse trace.list failed: {e!r}")

    traces = getattr(traces_resp, "data", None) or []
    print("# latency_percentiles.py self-test")
    print(f"GRAPH_TRACE_NAME={GRAPH_TRACE_NAME!r}")
    print(f"BRIEF_TRACE_NAME={BRIEF_TRACE_NAME!r}")
    print(f"GRAPH_SPAN_PREFIX={GRAPH_SPAN_PREFIX!r}")
    print("")
    if not traces:
        print("No recent traces found.")
        return 1

    for trace in traces:
        trace_id = getattr(trace, "id", "")
        trace_name = getattr(trace, "name", "")
        print(f"trace {trace_id} name={trace_name!r}")
        if not trace_id:
            continue
        try:
            obs_resp = client.api.observations.get_many(
                trace_id=trace_id,
                limit=50,
                fields="name,metadata,latency",
                expand_metadata="true",
            )
        except Exception as exc:
            print(f"  observations unavailable: {exc!r}")
            continue
        names = []
        for obs in getattr(obs_resp, "data", None) or []:
            metadata = getattr(obs, "metadata", None) or {}
            name = getattr(obs, "name", "") or ""
            if not name and isinstance(metadata, dict):
                name = str(metadata.get("span_name") or "")
            names.append(name)
        graph_names = [name for name in names if str(name).startswith(GRAPH_SPAN_PREFIX)]
        if graph_names:
            for name in graph_names:
                print(f"  span {name!r}")
        elif names:
            print("  spans " + ", ".join(repr(str(name)) for name in names[:8]))
        else:
            print("  no observations")

    try:
        client.shutdown()
    except Exception:
        pass
    return 0


def render_markdown(
    node_stats: dict[str, NodeStats],
    end_to_end_ms: list[float],
    costs_usd: list[float],
    sample_n: int,
    trace_name: str,
) -> str:
    e2e_p50 = _percentile(end_to_end_ms, 50.0)
    e2e_p95 = _percentile(end_to_end_ms, 95.0)
    total_cost = sum(costs_usd)
    mean_cost = (total_cost / len(costs_usd)) if costs_usd else 0.0

    lines: list[str] = []
    lines.append(f"<!-- generated by agentdocs/latency_percentiles.py against {trace_name!r}, n={sample_n} -->")
    lines.append("")
    lines.append("### Per-node latency (ms)")
    lines.append("")
    header = "| Metric | " + " | ".join(EXPECTED_NODES) + " |"
    sep = "|--------|" + "|".join(["----"] * len(EXPECTED_NODES)) + "|"
    lines.append(header)
    lines.append(sep)
    p50_row = "| p50 | " + " | ".join(_fmt_ms(node_stats[n].p50()) for n in EXPECTED_NODES) + " |"
    p95_row = "| p95 | " + " | ".join(_fmt_ms(node_stats[n].p95()) for n in EXPECTED_NODES) + " |"
    n_row = "| n | " + " | ".join(str(node_stats[n].n()) for n in EXPECTED_NODES) + " |"
    lines.extend([p50_row, p95_row, n_row])
    lines.append("")
    lines.append("### End-to-end latency (ms)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| p50 | {_fmt_ms(e2e_p50)} |")
    lines.append(f"| p95 | {_fmt_ms(e2e_p95)} |")
    lines.append(f"| n | {len(end_to_end_ms)} |")
    lines.append("")
    lines.append("### Cost (USD, sample total)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total cost across sample | ${total_cost:.4f} |")
    lines.append(f"| Mean cost per trace | ${mean_cost:.6f} |")
    lines.append(f"| Sample size | {len(costs_usd)} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute Langfuse latency p50/p95 + cost.")
    parser.add_argument("--n", type=int, default=50, help="Number of recent traces to sample (default 50).")
    parser.add_argument(
        "--trace-name",
        default=DEFAULT_TRACE_NAME,
        help=f"Trace name to filter on (default {DEFAULT_TRACE_NAME!r}).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="List recent trace/span names to confirm Langfuse naming before sampling.",
    )
    args = parser.parse_args(argv)
    if args.n <= 0:
        _die("--n must be positive.")
    if args.self_test:
        return self_test(min(args.n, 5))

    node_stats, end_to_end_ms, costs_usd = collect(args.n, args.trace_name)
    md = render_markdown(node_stats, end_to_end_ms, costs_usd, args.n, args.trace_name)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
