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

from app.schemas import Claim, LLMOutput, SourcePacket
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
        [claim_factory("A1c 7.2 then 6.4, trending downward.", ["lab:a1c-2025-01", "lab:a1c-2026-04"], claim_type="trend")]
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


def test_refusal_scope_drops_prose_action_phrase_in_claim_text(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory(
        "allergy:lists:42",
        resource_type="AllergyIntolerance",
        source_table="lists",
        label="Allergy",
        value="Penicillin",
        status="active",
    )
    out = llm_output_factory([
        claim_factory("Penicillin allergy documented — verify current status.", ["allergy:lists:42"])
    ])
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


# ---------- Slice B: source_value_mismatch (numbers + ISO dates) ----------


def test_source_value_mismatch_drops_wrong_med_dose(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory(
        "rx:1#med",
        source_table="prescriptions",
        resource_type="MedicationRequest",
        label="Active medication",
        value="Lisinopril",
        unit="10 mg",
        status="active",
    )
    out = llm_output_factory([claim_factory("Lisinopril 100 mg PO daily.", ["rx:1#med"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_source_value_match_allows_correct_med_dose(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory(
        "rx:1#med",
        source_table="prescriptions",
        resource_type="MedicationRequest",
        label="Active medication",
        value="Lisinopril",
        unit="10 mg",
        status="active",
    )
    out = llm_output_factory([claim_factory("Lisinopril 10 mg PO daily.", ["rx:1#med"])])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


def test_source_value_mismatch_drops_wrong_lab_value(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory(
        "lab:a1c-recent",
        source_table="procedure_result",
        resource_type="Observation",
        label="Hemoglobin A1c",
        value="8.4",
        unit="%",
        status=None,
    )
    out = llm_output_factory([claim_factory("Recent A1c is 6.4%.", ["lab:a1c-recent"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_source_value_match_allows_decimal_equivalence(
    packet_factory, claim_factory, llm_output_factory
):
    # Packet stores "8.4", claim writes "8.4" — match.
    # Also: "10" should match "10.0" (and vice versa).
    p = packet_factory(
        "lab:a1c-recent",
        source_table="procedure_result",
        resource_type="Observation",
        label="Hemoglobin A1c",
        value="8.4",
        unit="%",
        status=None,
    )
    out = llm_output_factory([claim_factory("Recent A1c is 8.4%.", ["lab:a1c-recent"])])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


def test_source_value_mismatch_drops_wrong_observed_date(
    packet_factory, claim_factory, llm_output_factory
):
    p = packet_factory(
        "lab:ldl-recent",
        source_table="procedure_result",
        resource_type="Observation",
        label="LDL Cholesterol",
        value="186",
        unit="mg/dL",
        observed_at="2026-04-20",
        status=None,
    )
    out = llm_output_factory([claim_factory("LDL 186 mg/dL on 2026-04-22.", ["lab:ldl-recent"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_trend_requires_values_from_both_sources(
    packet_factory, claim_factory, llm_output_factory
):
    p_old = packet_factory("lab:a1c-old", value="7.2", unit="%", status=None)
    p_new = packet_factory("lab:a1c-new", value="8.4", unit="%", status=None)
    # 8.9 is not in either packet — must drop.
    out = llm_output_factory([
        claim_factory(
            "A1c rose from 7.2 to 8.9.",
            ["lab:a1c-old", "lab:a1c-new"],
            claim_type="trend",
        )
    ])
    res = _verify(out, [p_old, p_new])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_trend_passes_when_both_values_in_evidence(
    packet_factory, claim_factory, llm_output_factory
):
    p_old = packet_factory("lab:a1c-old", value="7.2", unit="%", status=None)
    p_new = packet_factory("lab:a1c-new", value="8.4", unit="%", status=None)
    out = llm_output_factory([
        claim_factory(
            "A1c rose from 7.2 to 8.4.",
            ["lab:a1c-old", "lab:a1c-new"],
            claim_type="trend",
        )
    ])
    res = _verify(out, [p_old, p_new])
    assert res.verifier_status == "passed"


def test_source_id_numbers_are_ignored(
    packet_factory, claim_factory, llm_output_factory
):
    # Source id "rx:prescriptions:101" must NOT count as evidence for the
    # number 100. Without the id-strip, "100" inside "rx:prescriptions:101"
    # could be a false positive — we want a clean failure.
    p = packet_factory(
        "rx:prescriptions:101",
        source_table="prescriptions",
        resource_type="MedicationRequest",
        label="Active medication",
        value="Lisinopril",
        unit="10 mg",
        status="active",
    )
    out = llm_output_factory([claim_factory("Lisinopril 100 mg PO daily.", ["rx:prescriptions:101"])])
    res = _verify(out, [p])
    assert res.verifier_status == "failed"
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_absence_claim_skips_value_grounding(
    packet_factory, claim_factory, llm_output_factory
):
    # Absence claims don't carry numerical values from packets, so the rule
    # should not interfere with them.
    p = packet_factory(
        "allergy:0#nkda",
        source_table="lists",
        value="NKDA",
        status=None,
    )
    out = llm_output_factory([
        claim_factory("No known allergies on file.", ["allergy:0#nkda"], claim_type="absence")
    ])
    res = _verify(out, [p])
    assert res.verifier_status == "passed"


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
    # The dropped claim cites an unknown source_id (no packet index entry), so
    # _panels_for_dropped finds no packet → fallback wording is used.
    assert any(
        "dropped" in m.lower() and "review the relevant chart panel" in m.lower()
        for m in res.missing_data
    )


def test_dropped_message_names_medications_panel(
    packet_factory, claim_factory, llm_output_factory
):
    """A dropped claim citing a `prescriptions` packet should name the
    Medications panel in the missing_data line."""
    rx = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Lisinopril",
        value="Lisinopril 10 mg",
        status="active",
    )
    # Claim writes "100 mg" but the packet says "10 mg" → source_value_mismatch.
    out = llm_output_factory([
        claim_factory("Lisinopril 100 mg PO daily", ["rx:prescriptions:1"]),
    ])
    res = _verify(out, [rx])
    assert res.unsupported_dropped == 1
    assert any(
        "dropped" in m.lower() and "medications" in m.lower()
        for m in res.missing_data
    )


def test_dropped_message_combines_multiple_panels(
    packet_factory, claim_factory, llm_output_factory
):
    """Two dropped claims citing different source_tables should produce a
    combined `Labs and Medications`-style hint."""
    rx = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Lisinopril",
        value="Lisinopril 10 mg",
        status="active",
    )
    lab = packet_factory(
        "lab:procedure_result:14",
        resource_type="Observation",
        source_table="procedure_result",
        label="Hemoglobin A1c",
        value="8.4",
        unit="%",
        observed_at="2026-04-28",
        status="final",
    )
    out = llm_output_factory([
        claim_factory("Lisinopril 100 mg PO daily", ["rx:prescriptions:1"]),
        claim_factory("A1c 6.4% on 2026-04-28", ["lab:procedure_result:14"]),
    ])
    res = _verify(out, [rx, lab])
    assert res.unsupported_dropped == 2
    msg = next(m for m in res.missing_data if "dropped" in m.lower())
    assert "labs" in msg.lower()
    assert "medications" in msg.lower()


# ---------- caveat ISO date grounding ----------

def test_caveat_iso_date_must_be_in_evidence(packet_factory, claim_factory, patient_uuid):
    """A claim whose caveat carries an ISO date not present in any cited
    packet must be dropped — caveats can no longer carry hallucinated dates."""
    p = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Atorvastatin",
        value="Atorvastatin",
        observed_at="2025-10-15",
        last_updated="2025-10-15",
        status="active",
        freshness="stale",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Active prescription: Atorvastatin",
                claim_type="fact",
                source_ids=["rx:prescriptions:1"],
                # ISO date in caveat that is NOT in the packet
                caveat="last updated 2024-01-01 — may be out of date",
            )
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    assert res.unsupported_dropped == 1
    assert any(i.rule == "source_value_mismatch" for i in res.verifier_issues)


def test_caveat_with_correct_iso_date_passes(packet_factory, claim_factory, patient_uuid):
    """Caveat that names the packet's observed_at verbatim still passes."""
    p = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Atorvastatin",
        value="Atorvastatin",
        observed_at="2025-10-15",
        last_updated="2025-10-15",
        status="active",
        freshness="stale",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Active prescription: Atorvastatin",
                claim_type="fact",
                source_ids=["rx:prescriptions:1"],
                caveat="last updated 2025-10-15 — may be out of date",
            )
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    assert res.verifier_status == "passed"


def test_caveat_relative_thresholds_are_not_grounded(
    packet_factory, claim_factory, patient_uuid
):
    """Caveats commonly contain interpretive thresholds (`>90d ago`,
    `~3 months`). These are NOT subject to the number-grounding rule —
    only ISO dates are. Without this carve-out the staleness language
    the prompt requires would constantly false-positive."""
    p = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Atorvastatin",
        value="Atorvastatin",
        observed_at="2025-10-15",
        last_updated="2025-10-15",
        status="active",
        freshness="stale",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Active prescription: Atorvastatin",
                claim_type="fact",
                source_ids=["rx:prescriptions:1"],
                # `>90d ago` and `~3 months` — neither `90` nor `3` is in any
                # packet, but caveats are exempt from the number rule.
                caveat="last updated >90d ago — last refill ~3 months back",
            )
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    assert res.verifier_status == "passed"


# ---------- missing_data sanitizers ----------

def test_missing_data_drops_clinical_action_phrasing(
    packet_factory, claim_factory, patient_uuid
):
    """`missing_data` entries that carry clinical-action language are dropped
    by the verifier (constraint #9 extended to the missing_data field)."""
    p = packet_factory("lists:1#problem")
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[Claim(text="Active T2DM", claim_type="fact", source_ids=["lists:1#problem"])],
        missing_data=[
            "Reason for A1c rise and response plan",
            "Atorvastatin prescription is old — verify if still active",
            "Recent vital signs",  # benign — should survive
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-md")
    issue_rules = [i.rule for i in res.verifier_issues]
    assert issue_rules.count("missing_data_clinical_action") == 2
    # Benign category-only line survives.
    assert any("recent vital signs" in m.lower() for m in res.missing_data)
    # The "response plan" / "verify if still" lines must be gone.
    assert not any("response plan" in m.lower() for m in res.missing_data)
    assert not any("verify if still" in m.lower() for m in res.missing_data)


def test_missing_data_drops_invented_vaccine_name(
    packet_factory, claim_factory, patient_uuid
):
    """`missing_data` that mentions a vaccine name (Hepatitis A, influenza,
    tetanus, COVID-19) NOT present in any packet evidence is dropped — the
    deterministic backstop for the Hep A hallucination from the smoke."""
    pneumococcal = packet_factory(
        "immunization:immunizations:1",
        resource_type="Immunization",
        source_table="immunizations",
        label="Immunization",
        value="Pneumococcal polysaccharide PPSV23 (synthetic demo)",
        observed_at="2019-10-12",
        status="completed",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[],
        missing_data=[
            # Hallucinated entity names — none of these appear in the packet.
            "Immunization status beyond Hepatitis A — current status for "
            "influenza, tetanus, COVID-19 not documented",
            # Benign category-level statement — should survive.
            "Blood pressure readings not in supplied packets",
        ],
    )
    res = verify(out, [pneumococcal], patient_uuid_hash(patient_uuid), trace_id="t-md")
    assert any(i.rule == "missing_data_named_entity" for i in res.verifier_issues)
    assert not any("hepatitis" in m.lower() for m in res.missing_data)
    assert any("blood pressure" in m.lower() for m in res.missing_data)


def test_missing_data_keeps_entity_mentioned_in_packet(
    packet_factory, claim_factory, patient_uuid
):
    """If the entity name DOES appear in a packet's evidence text, the entry
    is kept — the rule is "invented entity," not "any entity."""
    pneumococcal = packet_factory(
        "immunization:immunizations:1",
        resource_type="Immunization",
        source_table="immunizations",
        label="Immunization",
        value="Pneumococcal polysaccharide PPSV23",
        observed_at="2019-10-12",
        status="completed",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[],
        missing_data=[
            # `pneumococcal` IS in the packet evidence — entry must survive.
            "Pneumococcal booster timing not documented in supplied packets",
        ],
    )
    res = verify(out, [pneumococcal], patient_uuid_hash(patient_uuid), trace_id="t-md")
    assert any("pneumococcal" in m.lower() for m in res.missing_data)
    assert not any(i.rule == "missing_data_named_entity" for i in res.verifier_issues)


def test_caveat_with_clinical_action_drops_claim(
    packet_factory, claim_factory, patient_uuid
):
    """A non-conflict claim whose caveat carries clinical-action language
    is dropped — the model can't route around constraint #9 by pushing
    recommendations into caveats. This was a real LLM emission seen in the
    2026-05-03 smoke ("verify if still current" in an Atorvastatin caveat)."""
    p = packet_factory(
        "rx:prescriptions:29",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Atorvastatin",
        value="Atorvastatin",
        observed_at="2025-10-15",
        last_updated="2025-10-15",
        status="active",
        freshness="stale",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Active prescription: Atorvastatin (last updated 2025-10-15)",
                claim_type="fact",
                source_ids=["rx:prescriptions:29"],
                caveat="last updated 2025-10-15 — verify if still current",
            )
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    assert res.unsupported_dropped == 1
    assert any(i.rule == "caveat_clinical_action" for i in res.verifier_issues)


def test_caveat_clinical_action_exempts_conflict_claims(
    packet_factory, claim_factory, patient_uuid
):
    """Conflict claims must recommend reconciliation per constraint #8, so
    their caveats are exempt from the clinical-action scan. Without this
    carve-out, every legitimate conflict claim would be dropped."""
    rx = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Lisinopril",
        value="Lisinopril 10 mg",
        status="active",
    )
    listed = packet_factory(
        "med:lists:1",
        resource_type="MedicationStatement",
        source_table="lists",
        label="Active medication",
        value="Lisinopril 10 mg PO daily",
        status="active",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Lisinopril appears in both medication list and active prescriptions",
                claim_type="conflict",
                source_ids=["med:lists:1", "rx:prescriptions:1"],
                caveat="Same medication in two sources — verify which is authoritative",
            )
        ],
    )
    res = verify(out, [rx, listed], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    # Conflict claim is NOT dropped — caveat scan skipped because claim_type=conflict.
    assert res.verifier_status == "passed"
    assert len(res.claims) == 1


def test_caveat_with_benign_staleness_passes(
    packet_factory, claim_factory, patient_uuid
):
    """Caveats with the standard staleness language ("may be out of date",
    "last updated >90d ago") are NOT clinical actions and must pass."""
    p = packet_factory(
        "rx:prescriptions:1",
        resource_type="MedicationRequest",
        source_table="prescriptions",
        label="Atorvastatin",
        value="Atorvastatin",
        observed_at="2025-10-15",
        last_updated="2025-10-15",
        status="active",
        freshness="stale",
    )
    out = LLMOutput(
        answer_type="pre_room_brief",
        claims=[
            Claim(
                text="Active prescription: Atorvastatin",
                claim_type="fact",
                source_ids=["rx:prescriptions:1"],
                caveat="last updated 2025-10-15 — may be out of date",
            )
        ],
    )
    res = verify(out, [p], patient_uuid_hash(patient_uuid), trace_id="t-cv")
    assert res.verifier_status == "passed"


def test_all_claims_dropped_surfaces_explicit_message(
    packet_factory, claim_factory, llm_output_factory
):
    """When every candidate claim fails verification, the brief must include
    an explicit "no verified claims" line so the rendered card doesn't
    silently look near-empty."""
    p = packet_factory("lists:1#problem")
    out = llm_output_factory([
        # Both claims cite an unknown source_id → both dropped.
        claim_factory("Unsupported A", ["lists:nope-1"]),
        claim_factory("Unsupported B", ["lists:nope-2"]),
    ])
    request_uuid = patient_uuid_hash(p.patient_uuid)
    res = verify(out, [p], request_uuid, trace_id="t-empty")
    assert res.verifier_status == "failed"
    assert len(res.claims) == 0
    assert any(
        "no verified claims could be produced" in m.lower()
        for m in res.missing_data
    )
