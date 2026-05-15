"""Diagnostic: reproduce a patient brief and dump the verifier's dropped-claim detail.

Plan_wk2_Claude_Next08 §W2 follow-up. The OpenEMR-side audit only logs
trace_id + verifier_status + source count -- it does NOT keep per-claim
detail. When a brief reports "N claim(s) failed verification and were
dropped", the *why* lives in the sidecar's VerifiedResponse.verifier_issues
list (each issue = {rule, detail}) and in Langfuse.

This script rebuilds a synthetic-but-faithful packet set for the Maria G.
demo chart, POSTs it to /v1/copilot/answer, and prints:
  - the verified claims that survived
  - every dropped claim's verifier rule + detail
  - the guideline-packet count (0 = the empty-question retrieval gap;
    Plan_Next08 W2's _derive_pre_room_query_from_packets fixes this, but
    the sidecar must be RESTARTED to pick up the nodes.py change since
    uvicorn runs without --reload)

Usage (from agent/copilot-api/):
    python scripts/diagnose_brief.py
    python scripts/diagnose_brief.py --question "Is her A1c controlled?"

Run it once against the current sidecar, restart the sidecar, run it
again -- the guideline-packet count and dropped-claim count should both
improve once the W2 retrieval fix is live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import uuid

SIDECAR = "http://127.0.0.1:8000"
GATEWAY_SECRET = "local-dev-shared-secret"
# Synthetic patient identity -- no real PII. The verifier's patient_binding
# rule checks sha256(packet.patient_uuid) == request.patient_uuid_hash, so
# the request hash MUST be the SHA-256 of the packet patient_uuid below or
# every packet is (incorrectly, for a diagnostic) rejected as cross-patient.
PATIENT_UUID = "diagnose-maria-g"
PATIENT_UUID_HASH = hashlib.sha256(PATIENT_UUID.encode("utf-8")).hexdigest()


def _packet(source_id, source_table, field, label, value, **extra):
    """Build one Wk1-shape SourcePacket dict. Required fields only + overrides."""
    base = {
        "source_id": source_id,
        "patient_uuid": PATIENT_UUID,
        "resource_type": extra.pop("resource_type", "Observation"),
        "source_table": source_table,
        "field": field,
        "label": label,
        "value": value,
        "freshness": extra.pop("freshness", "recent"),
        "status": extra.pop("status", "active"),
    }
    base.update(extra)
    return base


def build_maria_packets():
    """Faithful reconstruction of the Maria G. demo chart (from the dashboard
    paste): 3 problems, 1 allergy, 3 prescriptions, 1 immunization, 1 lab."""
    return [
        # Problems
        _packet("problem:lists:1", "lists", "diagnosis", "Medical problem",
                "Type 2 Diabetes", resource_type="Condition"),
        _packet("problem:lists:2", "lists", "diagnosis", "Medical problem",
                "Hypertension", resource_type="Condition"),
        _packet("problem:lists:3", "lists", "diagnosis", "Medical problem",
                "Hyperlipidemia", resource_type="Condition"),
        # Allergy
        _packet("allergy:lists:57", "lists", "allergy", "Allergy",
                "Penicillin", resource_type="AllergyIntolerance"),
        # Prescriptions
        _packet("rx:prescriptions:37", "prescriptions", "drug", "Active prescription",
                "Lisinopril", unit="10 mg", resource_type="MedicationRequest"),
        _packet("rx:prescriptions:36", "prescriptions", "drug", "Active prescription",
                "Metformin", unit="500 mg", resource_type="MedicationRequest"),
        _packet("rx:prescriptions:38", "prescriptions", "drug", "Active prescription",
                "Atorvastatin", unit="20 mg", resource_type="MedicationRequest"),
        # Immunization (the one that DID survive in the paste)
        _packet("immunization:immunizations:8", "immunizations", "vaccine",
                "Immunization", "Pneumococcal polysaccharide vaccine (PPSV23)",
                observed_at="2019-10-12", freshness="stale",
                resource_type="Immunization"),
        # Lab
        _packet("lab:procedure_result:1", "procedure_result", "result",
                "Lab result", "Hemoglobin A1c", observed_at="2026-05-04"),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", default=None,
                    help="Optional free-text question (default: pre_room_brief, no question)")
    ap.add_argument("--use-case", default="pre_room_brief")
    args = ap.parse_args()

    trace_id = str(uuid.uuid4())
    payload = {
        "trace_id": trace_id,
        "patient_uuid_hash": PATIENT_UUID_HASH,
        "use_case": args.use_case,
        "question": args.question,
        "packets": build_maria_packets(),
    }

    req = urllib.request.Request(
        f"{SIDECAR}/v1/copilot/answer",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-copilot-gateway-secret": GATEWAY_SECRET,
        },
        method="POST",
    )

    print(f"=== diagnose_brief: POST /v1/copilot/answer ===")
    print(f"trace_id   : {trace_id}")
    print(f"use_case   : {args.use_case}")
    print(f"question   : {args.question or '(none -- pre_room_brief)'}")
    print(f"packets    : {len(payload['packets'])} chart packets sent")
    print()

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Sidecar unreachable: {e.reason}")
        print("Is the sidecar running? cd agent/copilot-api ; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        sys.exit(1)

    # --- guideline retrieval signal ---------------------------------------
    # The brief response doesn't echo guideline_packets directly, but the
    # claims' source_ids reveal whether any guideline_chunk packets made it
    # into synthesis. Detection: any source_id cited by a surviving claim
    # that we did NOT send as a chart packet must be a retrieved guideline
    # chunk (corpus chunk IDs look like 'acip-pneumococcal-adults-2022-...',
    # 'ada-standards-2026-...', 'openfda-...' -- they have no fixed prefix,
    # so "not one of ours" is the reliable test). A pre-W2-fix sidecar
    # (empty-question retrieval) shows zero guideline sources.
    claims = body.get("claims", []) or []
    issues = body.get("verifier_issues", []) or []
    dropped = body.get("unsupported_dropped", 0)
    verifier_status = body.get("verifier_status", "?")
    answer_type = body.get("answer_type", "?")
    missing = body.get("missing_data", []) or []

    sent_source_ids = {p["source_id"] for p in payload["packets"]}
    guideline_sources = set()
    for c in claims:
        for sid in (c.get("source_ids") or []):
            if sid not in sent_source_ids:
                guideline_sources.add(sid)

    print(f"verifier_status    : {verifier_status}")
    print(f"answer_type        : {answer_type}")
    print(f"verified claims    : {len(claims)}")
    print(f"dropped (unsupported_dropped): {dropped}")
    print(f"verifier_issues    : {len(issues)}")
    print(f"guideline sources in surviving claims: {len(guideline_sources)}")
    print()

    if claims:
        print("--- VERIFIED CLAIMS (survived) ---")
        for i, c in enumerate(claims, 1):
            print(f"  {i}. [{c.get('claim_type', '?')}] {c.get('text', '')}")
            print(f"      source_ids: {c.get('source_ids', [])}")
        print()

    if issues:
        print("--- DROPPED CLAIMS / VERIFIER ISSUES (the 'N failed verification' detail) ---")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. rule:   {issue.get('rule', '?')}")
            print(f"     detail: {issue.get('detail', '')}")
        print()
    else:
        print("--- no verifier_issues in the response ---")
        print("  (If the brief UI said 'N claims dropped' but this is empty, the")
        print("   detail is only in Langfuse -- brief.php does not echo verifier_issues")
        print("   to the browser, only the unsupported_dropped count.)")
        print()

    if missing:
        print("--- missing_data (shown in the brief's 'Missing:' line) ---")
        for m in missing:
            print(f"  - {m}")
        print()

    # --- interpretation ---------------------------------------------------
    print("=== interpretation ===")
    if len(guideline_sources) == 0:
        print("  guideline sources = 0. Either the sidecar is running PRE-W2-fix code")
        print("  (restart it -- uvicorn has no --reload), OR retrieval genuinely")
        print("  returned nothing. Check the sidecar's stdout for the line:")
        print("  'evidence_retriever_node: derived pre-room query from N chart packets'")
        print("  -- if that line is absent, the sidecar is stale.")
    else:
        print(f"  guideline sources = {len(guideline_sources)} -- retrieval IS feeding")
        print("  synthesis. The W2 fix is live.")

    sys.exit(0)


if __name__ == "__main__":
    main()
