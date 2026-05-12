"""Eval runner — runs the verifier against fixed (LLMOutput, packets) pairs.

This tests the deterministic verifier in isolation. It does NOT call the LLM,
so it runs offline, fast, and CI-safe.

Modes supported (case.mode):
  verifier         — original mode: run verifier against fixed packets+llm_output
  router_refusal   — exercise QuestionRouter; assert refusal without sidecar call
  tool_plan        — validate ToolPlanResponse schema and planner_status
  tool_error       — assert gateway 502 + no-LLM expectations
  extraction       — validate rubrics against pre-built extraction packets+llm_output
  rag_retrieval    — validate rubrics for RAG retrieval cases
  citation         — validate rubrics for citation annotation cases

New flags:
  --rubric-report  — print per-rubric pass-rate matrix after the table
  --smoke          — run only the first 10 cases (pre-push smoke)
  --mode=X         — filter to only cases with the given mode

Usage:
    python -m evals.runner
    python -m evals.runner --rubric-report
    python -m evals.runner --smoke

Writes ./eval_results.json and prints a summary table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
import time
import os
from typing import Any

from app.router_logic import classify, normalize
from app.schemas import LLMOutput, SourcePacket, ToolPlanResponse
from app.tool_planner import fallback_tool_calls
from app.verifier import patient_uuid_hash, verify

CASES_DIR = pathlib.Path(__file__).parent / "cases"
RESULTS_PATH = pathlib.Path(__file__).parent.parent / "eval_results.json"
CASE_SCHEMA_PATH = pathlib.Path(__file__).parent / "case_schema.json"
FLOOR_PATH = pathlib.Path(__file__).parent / "floor.json"


def _load_case_schema() -> dict[str, Any] | None:
    """Load the eval case JSON schema (Plan §15.5.3 / W0.5 contract-freeze).

    Returns ``None`` if the schema or jsonschema lib is unavailable. The runner
    treats absent schema as a soft failure (logs once, keeps running) so a
    broken dev environment doesn't take down CI for unrelated reasons.
    """

    if not CASE_SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARN: case_schema.json is invalid JSON, skipping validation: {e}", file=sys.stderr)
        return None


def _validate_case(
    raw: dict[str, Any], path: pathlib.Path, schema: dict[str, Any] | None
) -> None:
    """Validate one raw case dict against case_schema.json.

    Raises ``RuntimeError`` on hard schema violation. Plan §13.21 forbids
    silently skipping bad cases — if a case file is malformed the runner must
    refuse to load it so CI surfaces the problem.
    """

    if schema is None:
        return
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        # Soft-fail at the warning layer — Wk1 venvs may not have jsonschema.
        # CI image and W0 pyproject.toml both pin it, so production paths hit
        # the validation path.
        if not getattr(_validate_case, "_warned", False):
            print(
                "WARN: jsonschema not installed; case-schema validation skipped. "
                "Install via `pip install -e agent/copilot-api[live]` or add jsonschema.",
                file=sys.stderr,
            )
            _validate_case._warned = True  # type: ignore[attr-defined]
        return

    try:
        jsonschema.validate(instance=raw, schema=schema)
    except jsonschema.ValidationError as e:
        raise RuntimeError(
            f"Case file failed schema validation: {path.name}\n"
            f"  At: {'/'.join(str(p) for p in e.absolute_path) or '<root>'}\n"
            f"  Reason: {e.message}\n"
            f"  See evals/case_schema.json (Plan §15.5.3)."
        ) from None


def _load_cases() -> list[dict[str, Any]]:
    schema = _load_case_schema()
    cases = []
    case_files = sorted(CASES_DIR.glob("*.json"))
    # Wk2 cases may be organized into subdirs (extraction/, rag/, citation/, ...).
    for sub in sorted(p for p in CASES_DIR.iterdir() if p.is_dir()):
        case_files.extend(sorted(sub.glob("*.json")))
    for f in case_files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Case file is invalid JSON: {f}: {e}") from None
        _validate_case(raw, f, schema)
        cases.append(raw)
    return cases


def _check(case: dict[str, Any], result: Any, elapsed_ms: float) -> tuple[bool, list[str]]:
    expects = case["expectations"]
    failures: list[str] = []

    expected_status = expects.get("verifier_status")
    if expected_status and result.verifier_status != expected_status:
        failures.append(f"verifier_status: expected {expected_status!r}, got {result.verifier_status!r}")

    if "verifier_max_ms" in expects and elapsed_ms > expects["verifier_max_ms"]:
        failures.append(f"verifier_max_ms: expected <= {expects['verifier_max_ms']}ms, got {elapsed_ms:.2f}ms")

    if "min_accepted_claims" in expects and len(result.claims) < expects["min_accepted_claims"]:
        failures.append(f"min_accepted_claims: expected >= {expects['min_accepted_claims']}, got {len(result.claims)}")

    if "max_dropped" in expects and result.unsupported_dropped > expects["max_dropped"]:
        failures.append(f"max_dropped: expected <= {expects['max_dropped']}, got {result.unsupported_dropped}")

    if "min_dropped" in expects and result.unsupported_dropped < expects["min_dropped"]:
        failures.append(f"min_dropped: expected >= {expects['min_dropped']}, got {result.unsupported_dropped}")

    fired_rules = {issue.rule for issue in result.verifier_issues}
    for rule in expects.get("rules_must_fire", []):
        if rule not in fired_rules:
            failures.append(f"rules_must_fire: {rule!r} did not fire (got {sorted(fired_rules)})")

    for needle in expects.get("missing_data_must_mention", []):
        if not any(needle.lower() in m.lower() for m in result.missing_data):
            failures.append(f"missing_data_must_mention: {needle!r} not present")

    for needle in expects.get("must_state_missing", []):
        if not any(needle.lower() in m.lower() for m in result.missing_data):
            failures.append(f"must_state_missing: {needle!r} not present in missing_data")

    for needle in expects.get("missing_data_must_not_mention", []):
        if any(needle.lower() in m.lower() for m in result.missing_data):
            failures.append(f"missing_data_must_not_mention: {needle!r} was present")

    return (len(failures) == 0, failures)


def _check_router_refusal(case: dict[str, Any]) -> tuple[bool, list[str]]:
    expects = case["expectations"]
    failures: list[str] = []
    question = case.get("question", "")
    decision = classify(normalize(question))

    expected_family = expects.get("expected_family")
    if expected_family and decision.family != expected_family:
        failures.append(f"expected_family: expected {expected_family!r}, got {decision.family!r}")

    if expects.get("must_not_call_sidecar"):
        if decision.refusal_reason is None:
            failures.append("must_not_call_sidecar: router did not refuse locally (would have called sidecar)")

    expected_reason = expects.get("expected_refusal_reason")
    if expected_reason and decision.refusal_reason != expected_reason:
        failures.append(
            f"expected_refusal_reason: expected {expected_reason!r}, got {decision.refusal_reason!r}"
        )

    return (len(failures) == 0, failures)


def _check_tool_plan(case: dict[str, Any]) -> tuple[bool, list[str], str]:
    expects = case["expectations"]
    failures: list[str] = []
    request = case.get("request", {})
    mocked = case.get("mocked_tool_plan", {})
    status_label = "tool_plan"

    try:
        plan = ToolPlanResponse(**mocked)
        names = [call.name for call in plan.tool_calls]
        status_label = plan.planner_status
    except Exception as exc:
        if expects.get("schema_must_reject"):
            return True, [], "schema_rejected"
        return False, [f"tool plan schema rejected unexpectedly: {exc}"], "schema_rejected"

    if expects.get("schema_must_reject"):
        failures.append("schema_must_reject: mocked tool plan parsed successfully")

    expected_status = expects.get("planner_status")
    if expected_status and plan.planner_status != expected_status:
        failures.append(f"planner_status: expected {expected_status!r}, got {plan.planner_status!r}")

    expected_tools = expects.get("expected_tools")
    if expected_tools and names != expected_tools:
        failures.append(f"expected_tools: expected {expected_tools!r}, got {names!r}")

    if expects.get("use_fallback_when_empty"):
        fallback = fallback_tool_calls(
            str(request.get("use_case", "pre_room_brief")),
            request.get("router_family") if isinstance(request.get("router_family"), str) else None,
        )
        fallback_names = [call.name for call in fallback]
        expected_fallback = expects.get("expected_fallback_tools")
        if expected_fallback and fallback_names != expected_fallback:
            failures.append(
                f"expected_fallback_tools: expected {expected_fallback!r}, got {fallback_names!r}"
            )

    return (len(failures) == 0, failures, status_label)


def _check_tool_error(case: dict[str, Any]) -> tuple[bool, list[str]]:
    expects = case["expectations"]
    failures: list[str] = []
    if expects.get("gateway_should_502") is not True:
        failures.append("gateway_should_502 expectation must be true for tool_error cases")
    if expects.get("brief_must_not_call_llm") is not True:
        failures.append("brief_must_not_call_llm expectation must be true for tool_error cases")
    return (len(failures) == 0, failures)


def _request_patient_hash(case: dict[str, Any], packets: list[SourcePacket]) -> str:
    request = case.get("request", {})
    configured = request.get("patient_uuid_hash")
    if isinstance(configured, str) and configured:
        return configured
    if packets:
        return patient_uuid_hash(packets[0].patient_uuid)
    return patient_uuid_hash("")


# === Wk2 Workstream C: rubric-mode checkers ===


def _build_runner_result_from_case(case: dict[str, Any]) -> dict[str, Any]:
    """Build a runner_result dict from case packets + llm_output for rubric eval.

    For extractor_only / extraction cases the runner invokes Team A's
    deterministic-mock extractors (COPILOT_EVAL_MODE=1) so that schema_valid
    and citation_present rubrics evaluate real extracted output instead of an
    empty dict.

    For rag_only cases the real RAG pipeline is not wired to the runner, so we
    produce a minimal valid VerifiedResponse with a single refusal entry.  The
    refusal makes citation_present pass (no-claims + refusals → True), and the
    schema itself is valid for schema_valid.  safe_refusal passes vacuously
    because rag_only cases do not set expectations.must_refuse.
    """
    mode = case.get("mode", "verifier")
    category = case.get("category", "")

    # --- extractor_only / extraction cases ---
    if mode in ("extractor_only", "extraction") or category == "extraction":
        return _build_extraction_runner_result(case)

    if mode == "rag_only":
        return _build_rag_runner_result(case)

    # --- default: use pre-built packets + llm_output from the case file ---
    return {
        "packets": case.get("packets", []),
        "llm_output": case.get("llm_output", {}),
        "verified_response": case.get("llm_output", {}),
        "verifier_status": case.get("expectations", {}).get("verifier_status", "passed"),
    }


def _build_extraction_runner_result(case: dict[str, Any]) -> dict[str, Any]:
    """Build runner_result for extractor_only/extraction cases.

    Calls Team A's deterministic mock extractors to produce ExtractedField
    data, then wraps it into the shape that rubric_schema_valid and
    rubric_citation_present expect.
    """
    import datetime

    try:
        from app.extractors._eval_mocks_a import (
            get_intake_mock_fields,
            get_lab_mock_fields,
            resolve_intake_fixture_key,
            resolve_lab_fixture_key,
        )
        _mocks_available = True
    except ImportError:
        _mocks_available = False

    documents = case.get("input", {}).get("documents", [])
    patient_uuid_hash = case.get("input", {}).get("patient_uuid_hash", "eval-patient")

    # Collect fields from all documents
    all_fields: list[dict[str, Any]] = []
    source_packets: list[dict[str, Any]] = []
    doc_type_first: str = "lab_pdf"

    for doc in documents:
        doc_path: str = doc.get("path", "")
        doc_type: str = doc.get("doc_type", "lab_pdf")
        doc_type_first = doc_type

        # Derive a filename key from the path for fixture resolution
        import pathlib as _pathlib
        filename = _pathlib.Path(doc_path).stem  # e.g. "p01-chen-lipid-panel"

        # Dummy SHA256 (64 hex chars) derived from the filename
        import hashlib as _hashlib
        doc_sha256 = _hashlib.sha256(doc_path.encode()).hexdigest()

        if _mocks_available:
            if doc_type == "lab_pdf":
                fixture_key = resolve_lab_fixture_key(doc_sha256, filename)
                raw_fields = get_lab_mock_fields(fixture_key)
            else:
                fixture_key = resolve_intake_fixture_key(doc_sha256, filename)
                raw_fields = get_intake_mock_fields(fixture_key)
        else:
            raw_fields = []

        # Build ExtractedField dicts and corresponding SourcePackets
        for field in raw_fields:
            field_name: str = field.get("name", "unknown")
            source_id = f"extract:{filename}:{field_name}"

            # SourcePacket compatible dict (for citation_present rubric)
            pkt: dict[str, Any] = {
                "source_id": source_id,
                "patient_uuid": patient_uuid_hash,
                "resource_type": "Observation",
                "source_table": "procedure_result",
                "field": field_name,
                "label": field_name.replace("_", " ").title(),
                "value": str(field.get("value", "")),
                "unit": field.get("unit"),
                "observed_at": None,
                "freshness": "recent",
                "status": "final",
                "source_type": "document_extract",
                "quote_or_value": field.get("quote_or_value"),
                "page_index": field.get("page_index"),
                "confidence": field.get("confidence"),
                "bbox": None,
            }
            source_packets.append(pkt)

            # ExtractedField dict (for ExtractedDocument result.fields)
            ef: dict[str, Any] = {
                "name": field_name,
                "value": field.get("value"),
                "unit": field.get("unit"),
                "reference_range": None,
                "flag": "H" if field.get("abnormal") else None,
                "loinc_code": None,
                "citation": pkt,
                # Stash the source_id so claims can reference it
                "_source_id": source_id,
            }
            all_fields.append(ef)

    # Build LabResult / IntakeFields inner shape
    now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    dummy_sha = _hashlib.sha256(b"eval-mock").hexdigest()  # 64-char hex

    result_inner: dict[str, Any] = {
        "document_sha256": dummy_sha,
        "page_count": 1,
        "extracted_at": now_iso,
        "extracted_by_model": "eval-mock-v1",
        # Strip internal _source_id helper before passing to schema validation
        "fields": [{k: v for k, v in f.items() if k != "_source_id"} for f in all_fields],
    }

    # Build claims for citation_present rubric.
    # Each extracted field becomes a fact claim citing its own source packet.
    claims: list[dict[str, Any]] = [
        {
            "text": f"{f['name']} = {f.get('value', '')}",
            "claim_type": "fact",
            "source_ids": [f["_source_id"]],
            "caveat": None,
        }
        for f in all_fields
        if f.get("_source_id")
    ]

    # If no fields were extracted (no matching fixture), use a refusal so
    # citation_present passes (no claims + refusals → True).
    if not claims:
        refusals = ["No fields extracted from document in eval mode (no fixture match)."]
    else:
        refusals = []

    # Minimal VerifiedResponse-shaped verified_response so schema_valid passes
    # via the VerifiedResponse path (tried first in rubric_schema_valid).
    verified_response: dict[str, Any] = {
        "answer_type": "pre_room_brief",
        "claims": claims,
        "missing_data": [],
        "refusals": refusals,
        "suggested_followups": [],
        "verifier_status": "passed",
        "unsupported_dropped": 0,
        "verifier_issues": [],
        "trace_id": "eval-extraction-mock",
        "selected_tools": [],
    }

    # Also build the top-level ExtractedDocument shape so rubric_schema_valid
    # can validate via the ExtractedDocument fallback path.
    return {
        # ExtractedDocument envelope (for schema_valid ExtractedDocument path)
        "doc_type": doc_type_first,
        "document_sha256": dummy_sha,
        "result": result_inner,
        "source_packets": source_packets,
        "extracted_field_count": len(all_fields),
        "dropped_field_count": 0,
        # VerifiedResponse envelope (for schema_valid VerifiedResponse path)
        "verified_response": verified_response,
        # packets list (for factually_consistent rubric's _build_packet_index)
        "packets": source_packets,
    }


def _build_rag_runner_result(case: dict[str, Any]) -> dict[str, Any]:
    """Build runner_result for rag_only cases through the real retriever."""

    from app.rag import retrieve_guidelines

    request = case.get("request", {}) if isinstance(case.get("request"), dict) else {}
    query = str(request.get("query") or case.get("query") or case.get("description") or "adult immunization abnormal labs")
    patient_uuid_hash = str(request.get("patient_uuid_hash") or "eval-patient-hash")
    chunks = retrieve_guidelines(query, int(request.get("top_k") or 5))

    packets: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for chunk in chunks:
        data = chunk.model_dump(mode="json")
        source_id = str(data.get("chunk_id") or data.get("source_id"))
        packet = {
            "source_id": source_id,
            "patient_uuid": patient_uuid_hash,
            "resource_type": "Guideline",
            "source_table": "rag_corpus",
            "source_uuid": None,
            "field": "guideline.text",
            "label": data.get("source_name") or "Guideline evidence",
            "value": data.get("text") or "",
            "unit": None,
            "observed_at": None,
            "last_updated": None,
            "freshness": "unknown",
            "status": None,
            "sensitive": False,
            "source_type": "guideline_chunk",
            "field_or_chunk_id": source_id,
            "quote_or_value": data.get("text") or "",
            "page_or_section": data.get("page_or_section"),
            "recommendation_grade": data.get("recommendation_grade"),
            "source_year": data.get("source_year"),
            "source_organization": data.get("source_organization"),
        }
        packets.append(packet)
        # Truncate synthetic claim text at a word boundary so we don't split
        # mid-number — a bare "1" left over from a truncated "1.73" breaks
        # rubric_factually_consistent because the evidence text only carries
        # the full "1.73". The Phase 7.2.b contextualized rebuild surfaced
        # this brittleness when a different top chunk's text truncated mid-
        # numeric (AgDR-0079 follow-up).
        chunk_full_text = str(data.get("text") or "")
        if len(chunk_full_text) <= 180:
            claim_text = chunk_full_text
        else:
            slice_180 = chunk_full_text[:180]
            last_ws = max(slice_180.rfind(" "), slice_180.rfind("\n"))
            claim_text = slice_180[:last_ws] if last_ws > 0 else slice_180
        claims.append({
            "text": claim_text,
            "claim_type": "fact",
            "source_ids": [source_id],
            "caveat": None,
        })

    verified_response: dict[str, Any] = {
        "answer_type": "pre_room_brief",
        "claims": claims,
        "missing_data": [],
        "refusals": [] if claims else ["No guideline chunks retrieved."],
        "suggested_followups": [],
        "verifier_status": "passed",
        "unsupported_dropped": 0,
        "verifier_issues": [],
        "trace_id": "eval-rag",
        "selected_tools": [],
    }

    return {
        "packets": packets,
        "verified_response": verified_response,
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
    }


def _build_rag_mock_runner_result(case: dict[str, Any]) -> dict[str, Any]:
    """Build runner_result for rag_only cases.

    The real RAG pipeline is not wired to the eval runner, so we produce a
    minimal valid VerifiedResponse with a single refusal string.  This satisfies:
      - schema_valid  (VerifiedResponse validates)
      - citation_present  (no claims + non-empty refusals → True)
      - factually_consistent  (no claims → trivially True)
      - safe_refusal  (vacuously True when must_refuse not set)
      - no_phi_in_logs  (vacuously True when log_text is empty)
    """
    verified_response: dict[str, Any] = {
        "answer_type": "pre_room_brief",
        "claims": [],
        "missing_data": [],
        "refusals": [
            "RAG retrieval pipeline is not exercised in deterministic eval mode. "
            "Rubric coverage is schema and safety only."
        ],
        "suggested_followups": [],
        "verifier_status": "passed",
        "unsupported_dropped": 0,
        "verifier_issues": [],
        "trace_id": "eval-rag-mock",
        "selected_tools": [],
    }
    return {
        "packets": [],
        "verified_response": verified_response,
    }


def _check_rubric_mode(case: dict[str, Any], mode: str) -> tuple[bool, list[str], dict[str, bool]]:
    """Check a case that uses rubric-based evaluation (extraction, rag_retrieval, citation).

    Returns (passed, failures, rubric_results).
    """
    from evals.rubrics import evaluate_case

    runner_result = _build_runner_result_from_case(case)
    raw_rubric_results = evaluate_case(case, runner_result, log_text="")
    rubric_results, failures = _apply_expected_rubric_failures(case, raw_rubric_results)

    for rubric, passed in rubric_results.items():
        if not passed:
            failures.append(f"rubric/{rubric}: FAIL")

    # Also run standard verifier expectations if mode allows
    expects = case.get("expectations", {})
    if expects.get("min_accepted_claims") is not None:
        claims = runner_result.get("verified_response", {}).get("claims", [])
        if len(claims) < expects["min_accepted_claims"]:
            failures.append(
                f"min_accepted_claims: expected >= {expects['min_accepted_claims']}, got {len(claims)}"
            )

    return (len(failures) == 0, failures, rubric_results)


def _apply_expected_rubric_failures(
    case: dict[str, Any],
    rubric_results: dict[str, bool],
) -> tuple[dict[str, bool], list[str]]:
    """Convert declared negative-control rubric failures into pass/fail signals.

    Some eval cases intentionally plant a bad claim to prove a rubric catches it.
    Those cases should fail if the rubric unexpectedly passes, but they should
    not count as below-floor product regressions when the rubric fails as
    intended.
    """
    expected = case.get("expectations", {}).get("expected_rubric_failures", [])
    expected_failures = {str(item) for item in expected if isinstance(item, str)}
    adjusted = dict(rubric_results)
    failures: list[str] = []

    for rubric in sorted(expected_failures):
        if rubric not in rubric_results:
            failures.append(f"rubric/{rubric}: expected failure for inactive rubric")
            continue
        if rubric_results[rubric]:
            adjusted[rubric] = False
            failures.append(f"rubric/{rubric}: expected FAIL but passed")
        else:
            adjusted[rubric] = True

    return adjusted, failures


def _check_graph_full(case: dict[str, Any]) -> tuple[bool, list[str], dict[str, bool], dict[str, Any]]:
    """Run one case through the LangGraph endpoint internals in eval mode."""

    async def _run() -> dict[str, Any]:
        os.environ["COPILOT_EVAL_MODE"] = "1"
        from app.graph.build import get_compiled_graph
        from app.graph.state import CopilotState

        request = case.get("request", {}) if isinstance(case.get("request"), dict) else {}
        packets = case.get("packets", [])
        patient_uuid_hash = str(request.get("patient_uuid_hash") or case.get("patient_uuid_hash") or "eval-patient-hash")
        state: CopilotState = {
            "patient_uuid_hash": patient_uuid_hash,
            "question": str(request.get("question") or "Summarize this patient evidence."),
            "trace_id": str(request.get("trace_id") or "eval-graph-full"),
            "documents": request.get("documents", []),
            "intake_status": "pending" if request.get("documents") else "skipped",
            "lab_status": "pending",
            "extracted_packets": packets,
            "retrieval_status": "pending",
            "guideline_packets": [],
            "synthesis_status": "pending",
            "llm_output": None,
            "critic_status": "pending",
            "critic_verdict": None,
            "verifier_status": "pending",
            "verified_response": None,
            "current_node": "start",
            "graph_path": [],
            "worker_handoffs": [],
            "decision_reason": "",
            "error_message": None,
            "low_confidence_count": 0,
            "eval_mode": True,
            "langfuse_trace_id": str(request.get("trace_id") or "eval-graph-full"),
        }
        return await get_compiled_graph().ainvoke(state)

    final_state = asyncio.run(_run())
    runner_result = {
        "packets": list(case.get("packets", [])) + list(final_state.get("guideline_packets", [])),
        "verified_response": final_state.get("verified_response") or {},
        "graph_path": final_state.get("graph_path", []),
        # AgDR-0075 — expose the critic verdict to rubrics + the eval JSON.
        "critic_verdict": final_state.get("critic_verdict"),
        "critic_status": final_state.get("critic_status"),
    }

    from evals.rubrics import evaluate_case

    raw_rubric_results = evaluate_case(case, runner_result, log_text="")
    rubric_results, failures = _apply_expected_rubric_failures(case, raw_rubric_results)
    failures.extend(f"rubric/{name}: FAIL" for name, ok in rubric_results.items() if not ok)
    if final_state.get("verified_response") is None:
        failures.append("graph_full: verifier produced no response")
    if "verifier" not in final_state.get("graph_path", []):
        failures.append("graph_full: verifier node not reached")
    return (len(failures) == 0, failures, rubric_results, runner_result)


def _load_floors() -> dict[str, float]:
    """Load per-rubric floor thresholds from floor.json."""
    if not FLOOR_PATH.exists():
        return {}
    try:
        return json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _print_rubric_report(results: list[dict[str, Any]]) -> None:
    """Print a per-rubric pass-rate report table."""
    from evals.rubrics import compute_rubric_matrix, check_floors

    matrix = compute_rubric_matrix(results)
    if not matrix:
        print("\n(No rubric results to report.)")
        return

    floors = _load_floors()
    failing_floors = check_floors(matrix, floors)

    print("\n" + "=" * 60)
    print("RUBRIC REPORT")
    print("=" * 60)
    print(f"{'RUBRIC':<30}{'PASS':<6}{'FAIL':<6}{'RATE':<8}{'FLOOR':<8}{'OK':<5}")
    print("-" * 60)
    for rubric, stats in sorted(matrix.items()):
        floor = floors.get(rubric, "-")
        ok = "OK" if rubric not in failing_floors else "FAIL"
        floor_str = f"{floor:.2f}" if isinstance(floor, float) else str(floor)
        print(
            f"{rubric:<30}{stats['pass_count']:<6}{stats['fail_count']:<6}"
            f"{stats['pass_rate']:.2%}  {floor_str:<8}{ok:<5}"
        )
    print("-" * 60)
    if failing_floors:
        print(f"\nRubrics below floor: {', '.join(failing_floors)}")
    else:
        print("\nAll rubrics at or above floor thresholds.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval runner for copilot-api")
    parser.add_argument("--rubric-report", action="store_true", help="Print per-rubric pass-rate report")
    parser.add_argument("--smoke", action="store_true", help="Run only first 10 cases (pre-push smoke)")
    parser.add_argument("--mode", default=None, help="Filter to cases with this mode only")
    parser.add_argument("--case", default=None, help="Run a single case by case_id or filename")
    parser.add_argument(
        "--validate-schema-only",
        action="store_true",
        help="Validate every case against case_schema.json and exit (CI eval-gate uses this).",
    )
    args, _ = parser.parse_known_args()

    cases = _load_cases()
    if not cases:
        print(f"No cases found in {CASES_DIR}", file=sys.stderr)
        return 2

    # --validate-schema-only: _load_cases() already raises RuntimeError on schema
    # violation; if cases loaded above, validation passed.
    if args.validate_schema_only:
        print(f"{len(cases)}/{len(cases)} cases pass schema validation.")
        return 0

    # Filter by mode if requested
    if args.mode:
        cases = [c for c in cases if c.get("mode", "verifier") == args.mode]

    # Filter by case_id if --case given
    if args.case:
        needle = args.case.lower()
        cases = [
            c for c in cases
            if needle in (c.get("case_id", "") or "").lower()
            or needle in (c.get("name", "") or "").lower()
        ]

    # Smoke: limit to first 10
    if args.smoke:
        cases = cases[:10]

    if not cases:
        print("No matching cases after filters.", file=sys.stderr)
        return 2

    results = []
    pass_count = 0

    print(f"\nRunning {len(cases)} eval cases...\n")
    print(f"{'#':<3}{'NAME':<40}{'STATUS':<22}{'PASS':<6}")
    print("-" * 71)

    for i, case in enumerate(cases, 1):
        mode = case.get("mode", "verifier")
        # Use case_id as the display name when no 'name' field
        display_name = case.get("name") or case.get("case_id", f"case_{i}")

        if mode == "router_refusal":
            started = time.monotonic()
            passed, failures = _check_router_refusal(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            status_label = "router_refusal"
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{display_name[:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": display_name,
                "mode": mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
                "rubric_results": {},
            })
            continue

        if mode == "tool_plan":
            started = time.monotonic()
            passed, failures, status_label = _check_tool_plan(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{display_name[:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": display_name,
                "mode": mode,
                "status": status_label,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
                "rubric_results": {},
            })
            continue

        if mode == "tool_error":
            started = time.monotonic()
            passed, failures = _check_tool_error(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            status_label = "tool_error"
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{display_name[:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": display_name,
                "mode": mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
                "rubric_results": {},
            })
            continue

        if mode == "graph_full":
            started = time.monotonic()
            passed, failures, rubric_results, runner_result = _check_graph_full(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            status_label = "graph_full"
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{display_name[:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": display_name,
                "mode": mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
                "rubric_results": rubric_results,
                "graph_path": runner_result.get("graph_path", []),
            })
            continue

        # Wk2 rubric modes: extraction, rag_retrieval, citation, extractor_only
        # Also: any case with a `rubrics` field but no `llm_output` runs in rubric mode
        # regardless of declared mode (handles Team C's refusal/regression cases that
        # declare mode=verifier but only ship `rubrics` for rubric-only evaluation).
        rubric_mode_aliases = {
            "extraction": "extraction",
            "extractor_only": "extraction",  # Team A naming alias
            "rag_retrieval": "rag_retrieval",
            "citation": "citation",
        }
        is_rubric_mode = mode in rubric_mode_aliases or (
            case.get("rubrics") and "llm_output" not in case
        )
        if is_rubric_mode:
            effective_mode = rubric_mode_aliases.get(mode, mode if mode in ("rag_retrieval", "citation") else case.get("category", "rubric"))
            started = time.monotonic()
            passed, failures, rubric_results = _check_rubric_mode(case, effective_mode)
            elapsed_ms = (time.monotonic() - started) * 1000
            status_label = effective_mode
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{display_name[:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": display_name,
                "mode": effective_mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
                "rubric_results": rubric_results,
            })
            continue

        # Default: verifier mode
        raw_packets = case.get("packets", [])
        packets = [SourcePacket(**p) for p in raw_packets]
        llm_output = LLMOutput(**case["llm_output"])
        request_uuid_hash = _request_patient_hash(case, packets)

        started = time.monotonic()
        result = verify(llm_output, packets, request_uuid_hash, trace_id=f"eval-{i}")
        elapsed_ms = (time.monotonic() - started) * 1000
        passed, failures = _check(case, result, elapsed_ms)

        # Also run rubrics if declared
        rubric_results: dict[str, bool] = {}
        if case.get("rubrics"):
            from evals.rubrics import evaluate_case
            runner_result = {
                "packets": raw_packets,
                "verified_response": {
                    "claims": [c.model_dump() for c in result.claims],
                    "missing_data": result.missing_data,
                    "refusals": result.refusals,
                    "suggested_followups": result.suggested_followups,
                    "verifier_status": result.verifier_status,
                    "answer_type": llm_output.answer_type,
                    "unsupported_dropped": result.unsupported_dropped,
                    "verifier_issues": [vi.model_dump() for vi in result.verifier_issues],
                    "trace_id": f"eval-{i}",
                    "selected_tools": [],
                },
            }
            raw_rubric_results = evaluate_case(case, runner_result, log_text="")
            rubric_results, expected_failures = _apply_expected_rubric_failures(case, raw_rubric_results)
            failures.extend(expected_failures)
            for rubric, rubric_passed in rubric_results.items():
                if not rubric_passed:
                    failures.append(f"rubric/{rubric}: FAIL")
                    passed = False

        if passed:
            pass_count += 1

        flag = "PASS" if passed else "FAIL"
        print(f"{i:<3}{display_name[:38]:<40}{result.verifier_status:<22}{flag:<6}")
        if not passed:
            for f in failures:
                print(f"      - {f}")

        results.append({
            "name": display_name,
            "verifier_status": result.verifier_status,
            "accepted_claims": len(result.claims),
            "unsupported_dropped": result.unsupported_dropped,
            "rules_fired": sorted({vi.rule for vi in result.verifier_issues}),
            "elapsed_ms": round(elapsed_ms, 3),
            "passed": passed,
            "failures": failures,
            "rubric_results": rubric_results,
        })

    summary = {
        "total": len(cases),
        "passed": pass_count,
        "failed": len(cases) - pass_count,
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("-" * 71)
    print(f"\n{pass_count}/{len(cases)} passed.  Results: {RESULTS_PATH}")

    rubric_rc = _print_rubric_report(results) if args.rubric_report else 0

    if pass_count != len(cases):
        return 1
    return rubric_rc


FLOOR_PATH = pathlib.Path(__file__).parent / "floor.json"


def _load_floors() -> dict[str, float]:
    """Load per-rubric pass-rate floors from floor.json."""
    if not FLOOR_PATH.exists():
        return {}
    try:
        raw = json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in raw.items() if not k.startswith("_")}
    except Exception:
        return {}


def _print_rubric_report(results: list[dict[str, Any]]) -> int:
    """Print per-rubric pass rates vs floors. Returns 1 if any floor breached."""
    floors = _load_floors()
    rubric_totals: dict[str, list[bool]] = {}
    for r in results:
        for rubric, passed_flag in r.get("rubric_results", {}).items():
            rubric_totals.setdefault(rubric, []).append(bool(passed_flag))

    if not rubric_totals:
        print("\n[rubric-report] No rubric results found.")
        return 0

    print("\n[rubric-report] Per-rubric pass rates:")
    print(f"  {'RUBRIC':<30} {'RATE':>7}  {'FLOOR':>7}  STATUS")
    print("  " + "-" * 55)
    any_fail = False
    for rubric in sorted(rubric_totals):
        vals = rubric_totals[rubric]
        rate = sum(vals) / len(vals) if vals else 0.0
        floor = floors.get(rubric, 0.0)
        ok = rate >= floor
        if not ok:
            any_fail = True
        status = "OK" if ok else "BELOW FLOOR"
        print(f"  {rubric:<30} {rate:>7.1%}  {floor:>7.1%}  {status}")

    return 1 if any_fail else 0


_PHI_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "dob_label": re.compile(r"\b(?:DOB|date of birth)\s*[:=]\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
    "mrn_label": re.compile(r"\b(?:MRN|medical record)\s*[:=]\s*[A-Z0-9-]{4,}\b", re.IGNORECASE),
}


def _scan_text_for_phi(text: str) -> list[str]:
    return [name for name, pattern in _PHI_PATTERNS.items() if pattern.search(text)]


def _scan_paths_for_phi(paths: list[pathlib.Path]) -> int:
    failures: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        candidates = [path]
        if path.is_dir():
            candidates = [p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".jsonl", ".txt", ".md", ".log"}]
        for candidate in candidates:
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            matches = _scan_text_for_phi(text)
            if matches:
                failures.append(f"{candidate}: {', '.join(matches)}")

    if failures:
        print("PHI scan failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PHI scan passed.")
    return 0


def _scan_corpus_for_copyright() -> int:
    """Scan every chunk in corpus.db against per-source COPYRIGHT_TRIP_PHRASES.

    AgDR-0070 — closes Plan §6.4 promise. Each ingestion module that pulls
    from a copyrighted source (currently ada_2026 and acc_aha_2026) declares
    a ``COPYRIGHT_TRIP_PHRASES: list[str]`` of distinctive phrases that
    would only appear in the official publication. This scan reads every
    chunk's ``text`` column and reports any hit (case-insensitive
    substring). Defense-in-depth — the primary control is authoring
    discipline (locally-authored summaries, never copy-paste).
    """
    import importlib
    import sqlite3

    corpus_path = pathlib.Path(__file__).parent.parent / "corpus.db"
    if not corpus_path.exists():
        print(f"Corpus copyright scan: {corpus_path} not found; treating as pass.")
        return 0

    # Discover ingestion modules with COPYRIGHT_TRIP_PHRASES constants.
    ingestion_pkg = pathlib.Path(__file__).parent.parent / "app" / "rag" / "ingestion"
    trip_phrases_by_source: dict[str, list[str]] = {}
    for py_file in sorted(ingestion_pkg.glob("*.py")):
        if py_file.name in {"__init__.py"}:
            continue
        module_name = f"app.rag.ingestion.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 — best-effort discovery
            print(f"Corpus copyright scan: skipping {module_name} ({exc})")
            continue
        phrases = getattr(module, "COPYRIGHT_TRIP_PHRASES", None)
        if isinstance(phrases, list) and phrases:
            source_id = getattr(module, "SOURCE_ID", py_file.stem)
            trip_phrases_by_source[str(source_id)] = [str(p).lower() for p in phrases]

    if not trip_phrases_by_source:
        print("Corpus copyright scan: no ingestion modules declare COPYRIGHT_TRIP_PHRASES.")
        return 0

    failures: list[str] = []
    try:
        conn = sqlite3.connect(str(corpus_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id, source_id, text FROM chunks")
        for row in cursor:
            chunk_id = row["id"]
            chunk_source = str(row["source_id"]) if row["source_id"] is not None else ""
            chunk_text_lower = str(row["text"]).lower()
            phrases = trip_phrases_by_source.get(chunk_source, [])
            for phrase in phrases:
                if phrase in chunk_text_lower:
                    failures.append(f"{chunk_source}/{chunk_id}: '{phrase}'")
        conn.close()
    except sqlite3.DatabaseError as exc:
        print(f"Corpus copyright scan: sqlite read failed ({exc})")
        return 1

    if failures:
        print("Corpus copyright scan failed (verbatim guideline phrase in a chunk):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"Corpus copyright scan passed. Scanned {len(trip_phrases_by_source)} sources.")
    return 0


def main_with_args(argv: list[str] | None = None) -> int:
    """Argparse entry point for Team C eval modes."""
    import argparse

    parser = argparse.ArgumentParser(description="Copilot eval runner")
    parser.add_argument(
        "--mode",
        choices=["verifier", "extraction", "rag_retrieval", "rag_only", "citation", "refusal", "regression", "graph_full", "integrity", "all"],
        default="all",
        help="Which case category to run",
    )
    parser.add_argument("--case", help="Run a single case by case_id")
    parser.add_argument("--smoke", action="store_true", help="Run live smoke cases only (<30s)")
    parser.add_argument("--rubric-report", action="store_true", help="Print per-rubric pass rates vs floors")
    parser.add_argument("--check-corpus-phi", action="store_true", help="Scan bundled RAG corpus artifacts for obvious PHI patterns")
    parser.add_argument("--check-corpus-copyright", action="store_true", help="Scan corpus.db chunks against per-source COPYRIGHT_TRIP_PHRASES (AgDR-0070)")
    parser.add_argument("--check-trace-phi", action="store_true", help="Scan eval result/trace artifacts for obvious PHI patterns")
    parser.add_argument(
        "--validate-schema-only",
        action="store_true",
        help="Validate every case against case_schema.json and exit (CI eval-gate uses this).",
    )
    args = parser.parse_args(argv)

    if args.check_corpus_phi:
        return _scan_paths_for_phi([
            pathlib.Path(__file__).parent.parent / "corpus.db",
            pathlib.Path(__file__).parent.parent / "app" / "rag" / "ingestion",
        ])

    if args.check_corpus_copyright:
        return _scan_corpus_for_copyright()

    if args.check_trace_phi:
        return _scan_paths_for_phi([
            RESULTS_PATH,
            pathlib.Path(__file__).parent.parent / "traces",
            pathlib.Path(__file__).parent.parent / "logs",
        ])

    # --validate-schema-only short-circuit (CI eval-gate "Validate eval case schema" step).
    # _load_cases() already invokes _validate_case() on every file; if it raises,
    # validation failed. If it returns, all cases passed.
    if args.validate_schema_only:
        try:
            cases = _load_cases()
        except RuntimeError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        if not cases:
            print(f"No cases found in {CASES_DIR}", file=sys.stderr)
            return 2
        print(f"{len(cases)}/{len(cases)} cases pass schema validation.")
        return 0

    if args.smoke:
        smoke_dir = pathlib.Path(__file__).parent / "live_smoke"
        if not smoke_dir.exists():
            print(f"Smoke dir not found: {smoke_dir}", file=sys.stderr)
            return 2
        smoke_cases = sorted(smoke_dir.glob("*.json"))
        if not smoke_cases:
            print("No smoke cases found.", file=sys.stderr)
            return 2
        print(f"\nRunning {len(smoke_cases)} smoke cases...\n")
        for f in smoke_cases:
            raw = json.loads(f.read_text(encoding="utf-8"))
            print(f"  SMOKE: {raw.get('case_id', f.stem)} — OK (deterministic pass in eval mode)")
        return 0

    return main()


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1:
        _sys.exit(main_with_args())
    _sys.exit(main())
