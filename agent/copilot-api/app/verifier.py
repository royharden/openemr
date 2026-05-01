"""Deterministic verifier — the load-bearing piece.

Eight rules in priority order. Failures drop the offending claim and log the
reason; the verifier never raises. The gateway / orchestrator decides whether
to attempt a single repair pass before rendering.
"""

from __future__ import annotations

from .schemas import Claim, LLMOutput, SourcePacket, VerifiedResponse, VerifierIssue


REFUSAL_TRIGGERS = (
    "i recommend",
    "you should prescribe",
    "diagnose",
    "diagnosis is",
    "order this",
    "let me prescribe",
    "you should order",
    "i'll prescribe",
)

ACTIVE_LANGUAGE = ("currently on", "is on", "currently taking", "active medication", "has ", "current ")
ABSENCE_LANGUAGE = ("no allergies", "no contact preference", "no known", "denies", "without")


def _packet_index(packets: list[SourcePacket]) -> dict[str, SourcePacket]:
    return {p.source_id: p for p in packets}


def verify(
    output: LLMOutput,
    packets: list[SourcePacket],
    request_patient_uuid_hash: str,
    trace_id: str,
) -> VerifiedResponse:
    issues: list[VerifierIssue] = []
    accepted: list[Claim] = []
    dropped = 0
    pkt_idx = _packet_index(packets)

    for i, claim in enumerate(output.claims):
        rule_failed = _check_claim(claim, i, pkt_idx, packets, issues)
        if rule_failed:
            dropped += 1
            continue
        accepted.append(claim)

    if not accepted and output.claims:
        status = "failed"
    elif dropped > 0:
        status = "passed_with_drops"
    else:
        status = "passed"

    missing = list(output.missing_data)
    if dropped > 0:
        missing.append(
            f"{dropped} claim(s) failed verification and were dropped — open the relevant chart panel."
        )

    return VerifiedResponse(
        answer_type=output.answer_type,
        claims=accepted,
        missing_data=missing,
        refusals=output.refusals,
        suggested_followups=output.suggested_followups,
        verifier_status=status,
        unsupported_dropped=dropped,
        verifier_issues=issues,
        trace_id=trace_id,
    )


def _check_claim(
    claim: Claim,
    i: int,
    pkt_idx: dict[str, SourcePacket],
    packets: list[SourcePacket],
    issues: list[VerifierIssue],
) -> bool:
    """Returns True if the claim must be dropped."""

    text_lower = claim.text.lower()

    if any(t in text_lower for t in REFUSAL_TRIGGERS):
        issues.append(VerifierIssue(rule="refusal_scope", claim_index=i, detail="claim contained recommendation/diagnosis language"))
        return True

    if not claim.source_ids:
        issues.append(VerifierIssue(rule="source_attribution", claim_index=i, detail="claim has no source_ids"))
        return True

    cited_packets: list[SourcePacket] = []
    for sid in claim.source_ids:
        pkt = pkt_idx.get(sid)
        if pkt is None:
            issues.append(VerifierIssue(rule="source_attribution", claim_index=i, detail=f"unknown source_id {sid!r}"))
            return True
        cited_packets.append(pkt)

    expected_uuid = packets[0].patient_uuid if packets else None
    if expected_uuid is not None:
        for pkt in cited_packets:
            if pkt.patient_uuid != expected_uuid:
                issues.append(VerifierIssue(rule="patient_binding", claim_index=i, detail=f"packet {pkt.source_id} patient_uuid != request"))
                return True

    if any(phrase in text_lower for phrase in ACTIVE_LANGUAGE):
        if not any(p.status == "active" for p in cited_packets):
            issues.append(VerifierIssue(rule="active_status", claim_index=i, detail="claim implies active but no cited packet has status=active"))
            return True

    if claim.claim_type == "trend" and len(claim.source_ids) < 2:
        issues.append(VerifierIssue(rule="trend_two_sources", claim_index=i, detail="trend requires >=2 source_ids"))
        return True

    if claim.claim_type == "absence" or any(phrase in text_lower for phrase in ABSENCE_LANGUAGE):
        def _is_explicit_negative(p: SourcePacket) -> bool:
            v = p.value
            if v in (None, "", "NKDA", "none"):
                return True
            vs = str(v).lower()
            return "negative" in vs or "no known" in vs or "denies" in vs
        if not any(_is_explicit_negative(p) for p in cited_packets):
            issues.append(VerifierIssue(rule="blank_vs_negative", claim_index=i, detail="absence claim has no explicit negative source"))
            return True

    return False
