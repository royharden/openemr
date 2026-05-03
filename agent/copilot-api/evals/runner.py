"""Eval runner — runs the verifier against fixed (LLMOutput, packets) pairs.

This tests the deterministic verifier in isolation. It does NOT call the LLM,
so it runs offline, fast, and CI-safe.

A subset of cases (those with `mode: "router_refusal"`) instead exercise the
gateway-side `QuestionRouter` (mirrored in `app.router_logic`) and assert that
no sidecar/LLM call would have been made — i.e. the router itself produced the
refusal.

Usage:
    python -m evals.runner

Writes ./eval_results.json and prints a summary table.
"""

from __future__ import annotations

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


def _load_cases() -> list[dict[str, Any]]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.json")):
        cases.append(json.loads(f.read_text(encoding="utf-8")))
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


def main() -> int:
    cases = _load_cases()
    if not cases:
        print(f"No cases found in {CASES_DIR}", file=sys.stderr)
        return 2

    results = []
    pass_count = 0

    print(f"\nRunning {len(cases)} eval cases against the verifier...\n")
    print(f"{'#':<3}{'NAME':<40}{'STATUS':<22}{'PASS':<6}")
    print("-" * 71)

    for i, case in enumerate(cases, 1):
        mode = case.get("mode", "verifier")
        if mode == "router_refusal":
            started = time.monotonic()
            passed, failures = _check_router_refusal(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            status_label = "router_refusal"
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{case['name'][:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": case["name"],
                "mode": mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
            })
            continue
        if mode == "tool_plan":
            started = time.monotonic()
            passed, failures, status_label = _check_tool_plan(case)
            elapsed_ms = (time.monotonic() - started) * 1000
            if passed:
                pass_count += 1
            flag = "PASS" if passed else "FAIL"
            print(f"{i:<3}{case['name'][:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": case["name"],
                "mode": mode,
                "status": status_label,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
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
            print(f"{i:<3}{case['name'][:38]:<40}{status_label:<22}{flag:<6}")
            if not passed:
                for f in failures:
                    print(f"      - {f}")
            results.append({
                "name": case["name"],
                "mode": mode,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "failures": failures,
            })
            continue

        packets = [SourcePacket(**p) for p in case["packets"]]
        llm_output = LLMOutput(**case["llm_output"])
        request_uuid_hash = _request_patient_hash(case, packets)

        started = time.monotonic()
        result = verify(llm_output, packets, request_uuid_hash, trace_id=f"eval-{i}")
        elapsed_ms = (time.monotonic() - started) * 1000
        passed, failures = _check(case, result, elapsed_ms)
        if passed:
            pass_count += 1

        flag = "PASS" if passed else "FAIL"
        print(f"{i:<3}{case['name'][:38]:<40}{result.verifier_status:<22}{flag:<6}")
        if not passed:
            for f in failures:
                print(f"      - {f}")

        results.append({
            "name": case["name"],
            "verifier_status": result.verifier_status,
            "accepted_claims": len(result.claims),
            "unsupported_dropped": result.unsupported_dropped,
            "rules_fired": sorted({i.rule for i in result.verifier_issues}),
            "elapsed_ms": round(elapsed_ms, 3),
            "passed": passed,
            "failures": failures,
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
    return 0 if pass_count == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
