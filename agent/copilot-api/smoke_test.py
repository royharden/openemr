"""Live smoke test: fixture packets -> real Anthropic call -> verifier.

Run from agent/copilot-api/:
    python smoke_test.py

Exits 0 on success. Prints the verified response for visual inspection.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

from app.orchestrator import process_brief
from app.schemas import BriefRequest, SourcePacket


def _fixture_packets() -> list[SourcePacket]:
    pid_uuid = "patient-uuid-fixture-1"
    return [
        SourcePacket(
            source_id="patient_data:row:1#identity",
            patient_uuid=pid_uuid,
            resource_type="Patient",
            source_table="patient_data",
            source_uuid="row-1",
            field="identity",
            label="Patient identity",
            value={"name": "Phil Belford", "age": 58, "sex": "M"},
            freshness="recent",
        ),
        SourcePacket(
            source_id="lists:42#problem",
            patient_uuid=pid_uuid,
            resource_type="Condition",
            source_table="lists",
            source_uuid="42",
            field="title",
            label="Active problem",
            value="Type 2 diabetes mellitus",
            status="active",
            freshness="recent",
            observed_at="2025-09-14",
        ),
        SourcePacket(
            source_id="lists:43#problem",
            patient_uuid=pid_uuid,
            resource_type="Condition",
            source_table="lists",
            source_uuid="43",
            field="title",
            label="Active problem",
            value="Essential hypertension",
            status="active",
            freshness="recent",
            observed_at="2024-11-02",
        ),
        SourcePacket(
            source_id="prescriptions:101#medication",
            patient_uuid=pid_uuid,
            resource_type="MedicationRequest",
            source_table="prescriptions",
            source_uuid="101",
            field="drug",
            label="Active medication",
            value="Metformin 500 mg PO BID",
            status="active",
            freshness="recent",
            observed_at="2026-02-10",
        ),
        SourcePacket(
            source_id="prescriptions:102#medication",
            patient_uuid=pid_uuid,
            resource_type="MedicationRequest",
            source_table="prescriptions",
            source_uuid="102",
            field="drug",
            label="Active medication",
            value="Lisinopril 20 mg PO daily",
            status="active",
            freshness="recent",
            observed_at="2026-01-20",
        ),
    ]


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        # llm.py loads .env at import; load again here in case the user runs it
        # before importing app modules.
        from dotenv import load_dotenv

        load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    packets = _fixture_packets()
    req = BriefRequest(
        trace_id=str(uuid.uuid4()),
        use_case="pre_room_brief",
        patient_uuid_hash="smoke-test-hash",
        packets=packets,
    )

    print(f"Model: {os.getenv('COPILOT_MODEL', '<default>')}")
    print(f"Trace: {req.trace_id}")
    print(f"Sending {len(packets)} packets...\n")

    verified = process_brief(req)
    payload = verified.model_dump()
    print(json.dumps(payload, indent=2, default=str))

    if verified.verifier_status == "failed":
        print("\nFAIL: verifier_status == failed", file=sys.stderr)
        return 1
    print(
        f"\nOK: verifier_status={verified.verifier_status}, "
        f"accepted={len(verified.claims)}, dropped={verified.unsupported_dropped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
