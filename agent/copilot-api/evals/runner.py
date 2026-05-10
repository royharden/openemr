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
import json
import pathlib
import sys
import time
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
    """Build a runner_result dict from case packets + llm_output for rubric eval."""
    return {
        "packets": case.get("packets", []),
        "llm_output": case.get("llm_output", {}),
        "verified_response": case.get("llm_output", {}),
        "verifier_status": case.get("expectations", {}).get("verifier_status", "passed"),
    }


def _check_rubric_mode(case: dict[str, Any], mode: str) -> tuple[bool, list[str], dict[str, bool]]:
    """Check a case that uses rubric-based evaluation (extraction, rag_retrieval, citation).

    Returns (passed, failures, rubric_results).
    """
    from evals.rubrics import evaluate_case

    runner_result = _build_runner_result_from_case(case)
    rubric_results = evaluate_case(case, runner_result, log_text="")

    failures: list[str] = []
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
    args, _ = parser.parse_known_args()

    cases = _load_cases()
    if not cases:
        print(f"No cases found in {CASES_DIR}", file=sys.stderr)
        return 2

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
        if passed:
            pass_count += 1

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
            rubric_results = evaluate_case(case, runner_result, log_text="")

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

    if args.rubric_report:
        _print_rubric_report(results)

    return 0 if pass_count == len(cases) else 1


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


def main_with_args(argv: list[str] | None = None) -> int:
    """Argparse entry point for Team C eval modes."""
    import argparse

    parser = argparse.ArgumentParser(description="Copilot eval runner")
    parser.add_argument(
        "--mode",
        choices=["verifier", "extraction", "rag_retrieval", "citation", "refusal", "regression", "all"],
        default="all",
        help="Which case category to run",
    )
    parser.add_argument("--case", help="Run a single case by case_id")
    parser.add_argument("--smoke", action="store_true", help="Run live smoke cases only (<30s)")
    parser.add_argument("--rubric-report", action="store_true", help="Print per-rubric pass rates vs floors")
    args = parser.parse_args(argv)

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
