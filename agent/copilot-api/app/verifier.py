"""Deterministic verifier — the load-bearing piece.

Eight per-claim rules in priority order plus three corpus-level checks
(stale-data labeling, sensitive-data caveat, lists/prescriptions duplicate
conflict surfacing). Failures drop the offending claim and log the reason; the
verifier never raises. The orchestrator decides whether to attempt a single
repair pass before rendering.
"""

from __future__ import annotations

import hashlib
import re

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
    "start them on",
    "start the patient on",
    "increase the dose",
    "decrease the dose",
    "adjust the dose",
    "discontinue",
    "stop taking",
    "refer the patient",
)

ACTIVE_LANGUAGE = ("currently on", "is on", "currently taking", "active medication", "has ", "current ")
ABSENCE_LANGUAGE = ("no allergies", "no contact preference", "no known", "denies", "without")
STALE_CAVEAT_HINTS = ("stale", "outdated", "old", "as of", "as-of", "last updated", "not recent", "may be out of date")


def _packet_index(packets: list[SourcePacket]) -> dict[str, SourcePacket]:
    return {p.source_id: p for p in packets}


def patient_uuid_hash(patient_uuid: str) -> str:
    return hashlib.sha256(patient_uuid.encode("utf-8")).hexdigest()[:12]


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
        rule_failed = _check_claim(claim, i, pkt_idx, request_patient_uuid_hash, issues)
        if rule_failed:
            dropped += 1
            continue
        accepted.append(claim)

    missing = list(output.missing_data)

    conflict_warnings = _detect_lists_rx_conflicts(packets, accepted)
    for w in conflict_warnings:
        issues.append(VerifierIssue(rule="lists_rx_conflict_unsurfaced", detail=w))
        missing.append(f"Possible duplicate medication conflict: {w}")

    if not accepted and output.claims:
        status = "failed"
    elif dropped > 0 or conflict_warnings:
        status = "passed_with_drops"
    else:
        status = "passed"

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
    request_patient_uuid_hash: str,
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

    for pkt in cited_packets:
        if patient_uuid_hash(pkt.patient_uuid) != request_patient_uuid_hash:
            issues.append(VerifierIssue(rule="patient_binding", claim_index=i, detail=f"packet {pkt.source_id} patient_uuid != request hash"))
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

    caveat_text = (claim.caveat or "").lower()
    if any(p.freshness == "stale" for p in cited_packets):
        if not any(hint in caveat_text or hint in text_lower for hint in STALE_CAVEAT_HINTS):
            issues.append(VerifierIssue(rule="stale_data_uncaveat", claim_index=i, detail="claim cites stale packet without staleness caveat"))
            return True

    if any(p.sensitive for p in cited_packets):
        if not claim.caveat:
            issues.append(VerifierIssue(rule="sensitive_data_uncaveat", claim_index=i, detail="claim cites sensitive packet without caveat"))
            return True

    return False


_MED_RX_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def _normalize_drug(value: object) -> str:
    if not isinstance(value, str):
        return ""
    tokens = _MED_RX_PATTERN.findall(value.lower())
    return tokens[0] if tokens else ""


def _detect_lists_rx_conflicts(packets: list[SourcePacket], accepted: list[Claim]) -> list[str]:
    """Detect medication packets that appear in both `lists` and `prescriptions`.

    Returns a list of warning strings naming the duplicated drug, but only when
    the LLM did NOT surface the duplication as a `conflict` claim citing both
    sources. This is the "lists vs prescriptions" duplicate conflict-surfacing
    rule from Slice J.
    """

    by_drug: dict[str, dict[str, list[SourcePacket]]] = {}
    for p in packets:
        if p.source_table not in {"lists", "prescriptions"}:
            continue
        if "Medication" not in p.resource_type:
            continue
        drug = _normalize_drug(p.value)
        if not drug:
            continue
        by_drug.setdefault(drug, {}).setdefault(p.source_table, []).append(p)

    warnings: list[str] = []
    for drug, by_table in by_drug.items():
        if "lists" not in by_table or "prescriptions" not in by_table:
            continue
        all_ids = {p.source_id for ps in by_table.values() for p in ps}
        surfaced = any(
            c.claim_type == "conflict" and all_ids.issubset(set(c.source_ids))
            for c in accepted
        )
        if surfaced:
            continue
        warnings.append(drug)
    return warnings
