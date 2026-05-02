"""Verifier rule coverage — one passing + one failing case per rule.

Rules in priority order (per plan_whole_opus47):
    1. schema_valid          (Pydantic boundary; tested in test_schemas.py)
    2. source_attribution    (claim.source_ids non-empty AND each id is known)
    3. patient_binding       (cited packet patient_uuid matches request set)
    4. active_status         ("active" language requires status=active)
    5. trend                 (claim_type=trend requires >=2 source_ids)
    6. blank_vs_negative     (absence requires explicit negative source)
    7. cross_patient         (cited source not in this turn's packet set)
    8. refusal_scope         (no diagnose / prescribe / order language)
"""

from __future__ import annotations

from app.schemas import SourcePacket
from app.verifier import patient_uuid_hash, verify


def _verify(llm_output, packets, *, request_uuid=None):
    if request_uuid is None:
        request_uuid = patient_uuid_hash(packets[0].patient_uuid if packets else "")
    return verify(llm_output, packets, request_uuid, trace_id="t-test")


# ---------- Rule 2: source_attribution ----------

def test_source_attribution_passes(packet_factory, claim_factory, llm_output_factory):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([claim_factory("Active T2DM", ["lists:1#problem"])])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"
    assert res.unsupported_dropped == 0


def test_source_attribution_fails_when_empty(packet_factory, claim_factory, llm_output_factory):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([claim_factory("Active T2DM", [])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_attribution" for i in res.verifier_issues)


def test_source_attribution_fails_on_unknown_id(packet_factory, claim_factory, llm_output_factory):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([claim_factory("Active T2DM", ["lists:9999#fake"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_attribution" for i in res.verifier_issues)


# ---------- Rule 3 / 7: patient_binding & cross_patient ----------

def test_patient_binding_fails_when_packet_uuid_differs(
    packet_factory, claim_factory, llm_output_factory, other_patient_uuid
):
    good = packet_factory("lists:1#problem")
    bad = packet_factory("lists:99#other", patient_uuid=other_patient_uuid)
    out = llm_output_factory([claim_factory("Diabetic", ["lists:99#other"])])
    res = _verify(out, [good, bad])
    assert res.verifier_status == "failed"
    assert any(i.rule == "patient_binding" for i in res.verifier_issues)


def test_patient_binding_uses_request_hash_not_first_packet(
    packet_factory, claim_factory, llm_output_factory, other_patient_uuid
):
    bad = packet_factory("lists:99#other", patient_uuid=other_patient_uuid)
    out = llm_output_factory([claim_factory("Diabetic", ["lists:99#other"])])
    res = _verify(out, [bad], request_uuid=patient_uuid_hash("patient-uuid-fixture"))
    assert res.verifier_status == "failed"
    assert any(i.rule == "patient_binding" for i in res.verifier_issues)


def test_cross_patient_id_not_in_packet_set_is_dropped(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("lists:1#problem")
    # Citing a source from a different patient's chart that wasn't included
    # in this turn's packets falls under source_attribution (unknown id).
    out = llm_output_factory([claim_factory("Diabetic", ["lists:5000#someone-else"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_attribution" for i in res.verifier_issues)


# ---------- Rule 4: active_status ----------

def test_active_status_passes_with_active_packet(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("rx:1#med", source_table="prescriptions", value="Metformin", status="active")
    out = llm_output_factory([claim_factory("Currently on Metformin", ["rx:1#med"])])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


def test_active_status_fails_without_active_packet(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("rx:2#med", source_table="prescriptions", value="Metformin", status="discontinued")
    out = llm_output_factory([claim_factory("Currently on Metformin", ["rx:2#med"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "active_status" for i in res.verifier_issues)


# ---------- Rule 5: trend ----------

def test_trend_passes_with_two_sources(packet_factory, claim_factory, llm_output_factory):
    p1 = packet_factory("lab:a1c-2025-01", value="7.2", status=None)
    p2 = packet_factory("lab:a1c-2026-04", value="6.4", status=None)
    out = llm_output_factory(
        [claim_factory("A1c trending downward over 16 mo", ["lab:a1c-2025-01", "lab:a1c-2026-04"], claim_type="trend")]
    )
    res = _verify(out, [p1, p2])
    assert res.verifier_status == "passed"


def test_trend_fails_with_single_source(packet_factory, claim_factory, llm_output_factory):
    p = packet_factory("lab:a1c-2026-04", value="6.4", status=None)
    out = llm_output_factory(
        [claim_factory("A1c trending downward", ["lab:a1c-2026-04"], claim_type="trend")]
    )
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "trend_two_sources" for i in res.verifier_issues)


# ---------- Rule 6: blank_vs_negative ----------

def test_absence_passes_with_explicit_nkda(packet_factory, claim_factory, llm_output_factory):
    p = packet_factory("allergy:0#nkda", source_table="lists", value="NKDA", status=None)
    out = llm_output_factory(
        [claim_factory("No known allergies on file", ["allergy:0#nkda"], claim_type="absence")]
    )
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


def test_absence_fails_when_packet_value_is_blank(
    packet_factory, claim_factory, llm_output_factory
):
    # A packet with a non-negative value can't justify "no allergies".
    p = packet_factory("allergy:1#unknown", source_table="lists", value="Penicillin", status=None)
    out = llm_output_factory(
        [claim_factory("No known allergies", ["allergy:1#unknown"], claim_type="absence")]
    )
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "blank_vs_negative" for i in res.verifier_issues)


# ---------- Rule 8: refusal_scope ----------

def test_refusal_scope_drops_diagnostic_recommendation(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([claim_factory("I recommend starting insulin therapy", ["lists:1#problem"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "refusal_scope" for i in res.verifier_issues)


def test_refusal_scope_drops_treatment_adjustment(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("rx:1#med", resource_type="MedicationRequest", source_table="prescriptions", value="Metformin")
    out = llm_output_factory([claim_factory("Increase the dose of Metformin.", ["rx:1#med"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "refusal_scope" for i in res.verifier_issues)


def test_refusal_scope_allows_descriptive_claim(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([claim_factory("Active Type 2 diabetes mellitus", ["lists:1#problem"])])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


# ---------- Slice J: stale_data_uncaveat ----------


def test_stale_data_uncaveat_drops_when_no_caveat(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("rx:5#stale", source_table="prescriptions", value="Lisinopril", freshness="stale")
    out = llm_output_factory([claim_factory("Currently on Lisinopril", ["rx:5#stale"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "stale_data_uncaveat" for i in res.verifier_issues)


def test_stale_data_uncaveat_passes_with_staleness_caveat(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("rx:5#stale", source_table="prescriptions", value="Lisinopril", freshness="stale")
    out = llm_output_factory([
        claim_factory(
            "Currently on Lisinopril",
            ["rx:5#stale"],
            caveat="Last updated >90d ago — may be out of date.",
        )
    ])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


# ---------- Slice J: sensitive_data_uncaveat ----------


def test_sensitive_packet_drops_uncaveat_claim(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("problem:9#mh", value="Generalized anxiety disorder", sensitive=True)
    out = llm_output_factory([claim_factory("Active problem: GAD", ["problem:9#mh"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "sensitive_data_uncaveat" for i in res.verifier_issues)


def test_sensitive_packet_passes_with_caveat(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("problem:9#mh", value="Generalized anxiety disorder", sensitive=True)
    out = llm_output_factory([
        claim_factory(
            "Active problem: GAD",
            ["problem:9#mh"],
            caveat="Sensitive — confirm in chart before discussion.",
        )
    ])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


# ---------- Slice J: lists_rx_conflict_unsurfaced ----------


def test_lists_rx_duplicate_flagged_when_not_surfaced_as_conflict(
    packet_factory, claim_factory, llm_output_factory
):
    a = packet_factory("med:lists:5", resource_type="MedicationStatement", source_table="lists", value="Lisinopril 10mg daily")
    b = packet_factory("rx:prescriptions:22", resource_type="MedicationRequest", source_table="prescriptions", value="lisinopril")
    out = llm_output_factory([claim_factory("Currently on Lisinopril 10mg", ["med:lists:5"])])
    res = _verify(out, [a, b])
    assert res.verifier_status == "passed_with_drops"
    assert any(i.rule == "lists_rx_conflict_unsurfaced" for i in res.verifier_issues)
    assert any("lisinopril" in m.lower() for m in res.missing_data)


def test_lists_rx_duplicate_silent_when_surfaced_as_conflict(
    packet_factory, claim_factory, llm_output_factory
):
    a = packet_factory("med:lists:5", resource_type="MedicationStatement", source_table="lists", value="Lisinopril 10mg daily")
    b = packet_factory("rx:prescriptions:22", resource_type="MedicationRequest", source_table="prescriptions", value="lisinopril")
    out = llm_output_factory([
        claim_factory(
            "Lisinopril appears in both the problem-list med entry and the active prescription record.",
            ["med:lists:5", "rx:prescriptions:22"],
            claim_type="conflict",
            caveat="Reconcile before prescribing.",
        )
    ])
    res = _verify(out, [a, b])
    assert res.verifier_status == "passed"
    assert not any(i.rule == "lists_rx_conflict_unsurfaced" for i in res.verifier_issues)


# ---------- aggregate behavior ----------

def test_drops_unsupported_keeps_supported(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory("lists:1#problem")
    out = llm_output_factory(
        [
            claim_factory("Active T2DM", ["lists:1#problem"]),
            claim_factory("Active hypertension", ["lists:does-not-exist"]),
        ]
    )
    res = _verify(out, [p])
    assert res.verifier_status == "passed_with_drops"
    assert res.unsupported_dropped == 1
    assert len(res.claims) == 1
    assert any("dropped" in m.lower() for m in res.missing_data)
