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
import unicodedata

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

# Clinical-action phrases that get pushed into prose fields (claim.text,
# claim.caveat, missing_data) to evade the existing REFUSAL_TRIGGERS gate. Each
# phrase here was lifted from a real LLM emission seen in the 2026-05-02 /
# 2026-05-03 smoke walkthroughs against Maria G.'s chart. Applied to
# `claim.text` / `claim.caveat` (drops the claim) and `missing_data` entries (drops the
# entry) — every LLM-emitted prose surface that survives into rendering must
# be subject to the same prohibition the prompt's constraint #9 promises.
PROSE_ACTION_PHRASES = (
    "recommend review",
    "verify if still active",
    "verify if still current",
    "verify if still",
    "verify which is authoritative",
    "verify current status",
    "confirm current status",
    "response plan",
    "consider alternatives",
    "if considering alternatives",
    "cross-reactivity",
)
# Note: "reconcile sources" / "reconcile source" are intentionally NOT on
# this list. Constraint #8 in brief_v1.txt explicitly REQUIRES the LLM to
# "recommend reconciliation in the caveat" for conflict claims, so banning
# that phrasing would directly contradict another rule.

# Clinical entity keywords commonly hallucinated in `missing_data` prose. Each
# entry is matched case-insensitively against the missing_data line; if a
# keyword appears in the line but does NOT appear in any cited packet's
# evidence text, the line is dropped. This is the deterministic backstop for
# `brief_v1.txt` constraint #15 ("missing_data honesty").
CLINICAL_ENTITY_KEYWORDS = (
    # Vaccines (the most common hallucination class — see plan_next03 finding 2)
    "hepatitis", "hep a", "hep b", "hep c", "hpv", "influenza",
    "tetanus", "tdap", "diphtheria", "covid", "covid-19", "coronavirus",
    "mmr", "varicella", "shingles", "zoster", "pneumococcal", "ppsv",
    "prevnar", "rotavirus", "rabies", "meningococcal", "polio",
    # Common drugs
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "losartan",
    "simvastatin", "rosuvastatin", "warfarin", "insulin", "glipizide",
    "albuterol", "amoxicillin", "azithromycin", "penicillin", "ibuprofen",
    "acetaminophen", "aspirin",
    # Common labs / panels
    "a1c", "hba1c", "ldl", "hdl", "triglycerides", "creatinine", "egfr",
    "tsh", "psa",
    # Common conditions
    "diabetes", "hypertension", "hyperlipidemia", "asthma", "copd",
)


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
    dropped_indexes: list[int] = []
    pkt_idx = _packet_index(packets)

    for i, claim in enumerate(output.claims):
        rule_failed = _check_claim(claim, i, pkt_idx, request_patient_uuid_hash, issues)
        if rule_failed:
            dropped += 1
            dropped_indexes.append(i)
            continue
        accepted.append(claim)

    missing, missing_sanitizer_drops = _sanitize_missing_data(
        list(output.missing_data), packets, issues
    )

    conflict_warnings = _detect_lists_rx_conflicts(packets, accepted)
    for w in conflict_warnings:
        issues.append(VerifierIssue(rule="lists_rx_conflict_unsurfaced", detail=w))
        missing.append(f"Possible duplicate medication conflict: {w}")

    if not accepted and output.claims:
        status = "failed"
        # All candidate claims were dropped by the verifier. Surface this
        # explicitly so the rendered brief doesn't mislead the user with a
        # near-empty card and only a generic "dropped" line — make it clear
        # that claims existed but none survived verification.
        missing.append(
            "No verified claims could be produced for this turn — all candidate "
            "claims failed verification. Open the chart panels directly."
        )
    elif dropped > 0 or conflict_warnings or missing_sanitizer_drops > 0:
        status = "passed_with_drops"
    else:
        status = "passed"

    if dropped > 0:
        panels = _panels_for_dropped(dropped_indexes, output.claims, pkt_idx)
        if panels:
            if len(panels) == 1:
                panel_phrase = panels[0]
            elif len(panels) == 2:
                panel_phrase = f"{panels[0]} and {panels[1]}"
            else:
                panel_phrase = ", ".join(panels[:-1]) + f", and {panels[-1]}"
            missing.append(
                f"{dropped} claim(s) failed verification and were dropped — review the {panel_phrase} panel(s)."
            )
        else:
            missing.append(
                f"{dropped} claim(s) failed verification and were dropped — review the relevant chart panel."
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

    text_action_hit = next(
        (t for t in REFUSAL_TRIGGERS if t in text_lower),
        None,
    ) or next(
        (p for p in PROSE_ACTION_PHRASES if p in text_lower),
        None,
    )
    if text_action_hit is not None:
        issues.append(VerifierIssue(
            rule="refusal_scope",
            claim_index=i,
            detail=f"claim contained clinical-action language {text_action_hit!r}",
        ))
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

    # Caveat clinical-action scan. Conflict claims are exempt because
    # constraint #8 requires them to recommend reconciliation in the caveat
    # ("reconcile sources" / similar). Every other claim type's caveat is
    # subject to the same prose-action prohibition the missing_data sanitizer
    # applies — without this the model can route around constraint #9 by
    # pushing recommendations into caveats instead of claim text.
    if claim.claim_type != "conflict" and claim.caveat:
        caveat_lower = claim.caveat.lower()
        action_hit = next(
            (t for t in REFUSAL_TRIGGERS if t in caveat_lower),
            None,
        ) or next(
            (p for p in PROSE_ACTION_PHRASES if p in caveat_lower),
            None,
        )
        if action_hit is not None:
            issues.append(VerifierIssue(
                rule="caveat_clinical_action",
                claim_index=i,
                detail=f"claim caveat contained clinical-action phrase {action_hit!r}",
            ))
            return True

    if claim.claim_type in ("fact", "trend", "conflict"):
        mismatch = _check_source_value_grounding(claim, cited_packets)
        if mismatch is not None:
            issues.append(VerifierIssue(rule="source_value_mismatch", claim_index=i, detail=mismatch))
            return True

    return False


# ---------- source-value grounding (numbers + ISO dates) ----------

# Match plain numbers but reject digits glued onto letters (so we don't pick up
# the "5" inside "rx:prescriptions:5" or the "3" inside "PPSV23" — but we DO
# pick up "10" in "10 mg"). The leading/trailing assertions use word boundaries
# in a way that excludes letter-adjacent digits.
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d.])(\d+(?:\.\d+)?)(?![A-Za-z\d])")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text)
    # Unicode dashes -> ASCII hyphen
    norm = re.sub(r"[‐-―−]", "-", norm)
    # collapse whitespace
    norm = re.sub(r"\s+", " ", norm)
    return norm.strip().lower()


def _evidence_text(packet: SourcePacket) -> str:
    parts: list[str] = [
        packet.label or "",
        str(packet.value) if packet.value is not None else "",
        packet.unit or "",
        packet.observed_at or "",
        packet.last_updated or "",
        packet.status or "",
        packet.field or "",
    ]
    return _normalize_text(" ".join(p for p in parts if p))


def _strip_source_ids(text: str, source_ids: list[str]) -> str:
    """Remove source_id substrings so digits inside IDs (`prescriptions:101`) do
    not count as claim numbers."""
    out = text
    for sid in source_ids:
        if sid:
            out = out.replace(sid.lower(), " ")
    return out


def _extract_numbers(text: str) -> list[str]:
    raw = _NUMBER_RE.findall(text)
    out: list[str] = []
    for n in raw:
        # Normalize trailing zeros: 10 == 10.0 == 10.00
        if "." in n:
            try:
                f = float(n)
                if f.is_integer():
                    out.append(str(int(f)))
                else:
                    out.append(str(f).rstrip("0").rstrip("."))
            except ValueError:
                out.append(n)
        else:
            out.append(n)
    return out


def _evidence_has_number(evidence_texts: list[str], number: str) -> bool:
    """`10` matches `10`, `10.0`, `10mg`, ` 10 `, `10/`. Does not match `100`."""
    # Build candidate forms to match.
    candidates = {number, f"{number}.0"}
    if "." in number:
        try:
            f = float(number)
            if f.is_integer():
                candidates.add(str(int(f)))
        except ValueError:
            pass
    for ev in evidence_texts:
        for cand in candidates:
            # Reuse the number regex on the evidence so we get the same
            # word-boundary behavior (won't match `10` inside `100`).
            if any(found == cand or found == f"{cand}.0" for found in _NUMBER_RE.findall(ev)):
                return True
    return False


def _extract_iso_dates(text: str) -> list[str]:
    return _ISO_DATE_RE.findall(text)


def _check_source_value_grounding(claim: Claim, cited_packets: list[SourcePacket]) -> str | None:
    """Return a detail string if the claim text contains a number or ISO date
    that does not appear in any cited packet's evidence; else None.

    Conservative-by-design: only checks numbers + ISO dates. Free-prose
    overlap (synonym checks like elevated/high/abnormal) is intentionally
    out of scope for v1 to avoid false positives.

    Caveats are also scanned, but only for ISO dates — numbers in caveats are
    often interpretive thresholds ("`>90d ago`", "`~3 months`") that won't
    appear in the packet by design, so enforcing free-number grounding there
    would false-positive on legitimate staleness language.
    """
    claim_text_norm = _normalize_text(claim.text)
    if not claim_text_norm:
        return None
    # Strip source_ids before number extraction so `prescriptions:101` doesn't
    # contribute `101` as a claim number.
    claim_for_numbers = _strip_source_ids(claim_text_norm, claim.source_ids)
    evidence_texts = [_evidence_text(p) for p in cited_packets]

    for n in _extract_numbers(claim_for_numbers):
        if not _evidence_has_number(evidence_texts, n):
            return f"claim text contains number {n!r} not present in any cited source packet"

    for d in _extract_iso_dates(claim_text_norm):
        if not any(d in ev for ev in evidence_texts):
            return f"claim text contains ISO date {d!r} not present in any cited source packet"

    caveat_norm = _normalize_text(claim.caveat or "")
    for d in _extract_iso_dates(caveat_norm):
        if not any(d in ev for ev in evidence_texts):
            return f"claim caveat contains ISO date {d!r} not present in any cited source packet"

    return None


# ---------- missing_data prose sanitizer ----------


def _sanitize_missing_data(
    raw: list[str],
    packets: list[SourcePacket],
    issues: list[VerifierIssue],
) -> tuple[list[str], int]:
    """Drop missing_data entries that either contain clinical-action language
    or invent specific clinical entity names not present in any packet.

    Returns (kept_entries, dropped_count). The dropped count feeds into the
    status logic so a turn whose only verifier complaint is sanitizer drops
    still surfaces as `passed_with_drops` (the LLM's prose was untrustworthy
    on a field the verifier doesn't otherwise gate).

    Two rules:
      1. `missing_data_clinical_action` — entry contains REFUSAL_TRIGGERS
         language ("recommend review", "increase the dose", "verify if still
         active", etc.). Constraint #9 in the prompt forbids treatment
         recommendations in claims; this extends that prohibition to the
         missing_data field, which the rest of the verifier doesn't gate.
      2. `missing_data_named_entity` — entry mentions a clinical entity name
         (vaccine, drug, lab, condition) from CLINICAL_ENTITY_KEYWORDS that
         does not appear in any packet's evidence text. This is the
         deterministic backstop for the Hep A hallucination found in the
         2026-05-02 smoke walkthrough.
    """
    if not raw:
        return [], 0

    evidence_pool = " ".join(_evidence_text(p) for p in packets)
    kept: list[str] = []
    dropped = 0

    for idx, entry in enumerate(raw):
        if not isinstance(entry, str) or not entry.strip():
            continue
        entry_lower = entry.lower()

        # Rule 1: clinical-action language.
        action_hit = next(
            (t for t in REFUSAL_TRIGGERS if t in entry_lower),
            None,
        ) or next(
            (p for p in PROSE_ACTION_PHRASES if p in entry_lower),
            None,
        )
        if action_hit is not None:
            issues.append(
                VerifierIssue(
                    rule="missing_data_clinical_action",
                    detail=(
                        f"missing_data[{idx}] contained clinical-action "
                        f"language {action_hit!r}; entry dropped"
                    ),
                )
            )
            dropped += 1
            continue

        # Rule 2: named clinical entity not in any packet evidence.
        entity_hit = next(
            (
                kw
                for kw in CLINICAL_ENTITY_KEYWORDS
                if kw in entry_lower and kw not in evidence_pool
            ),
            None,
        )
        if entity_hit is not None:
            issues.append(
                VerifierIssue(
                    rule="missing_data_named_entity",
                    detail=(
                        f"missing_data[{idx}] mentioned {entity_hit!r} which "
                        f"is not in any packet evidence; entry dropped"
                    ),
                )
            )
            dropped += 1
            continue

        kept.append(entry)

    return kept, dropped


# ---------- panel-name hint for dropped-claim message ----------

# Maps `(source_table, resource_type)` to a friendly chart panel name. The
# `lists` table holds problems, allergies, AND medications — disambiguated by
# resource_type. Other source tables map directly. Future source_table values
# (procedure_report, procedure_order, form_encounter) are pre-mapped so the
# helper is forward-compatible with builders that haven't shipped yet.
_SOURCE_TABLE_TO_PANEL: dict[str, str] = {
    "prescriptions":    "Medications",
    "procedure_result": "Labs",
    "procedure_report": "Labs",
    "procedure_order":  "Labs",
    "immunizations":    "Immunizations",
    "patient_data":     "Demographics",
    "form_encounter":   "Encounters",
}

_LISTS_RESOURCE_TO_PANEL: dict[str, str] = {
    "Condition":          "Problems",
    "AllergyIntolerance": "Allergies",
    "MedicationStatement": "Medications",
}


def _panel_for_packet(packet: SourcePacket) -> str:
    """Map a single packet to a friendly panel name; returns '' if unknown."""
    if packet.source_table == "lists":
        return _LISTS_RESOURCE_TO_PANEL.get(packet.resource_type, "Problems")
    return _SOURCE_TABLE_TO_PANEL.get(packet.source_table, "")


def _panels_for_dropped(
    dropped_claim_indexes: list[int],
    claims: list[Claim],
    pkt_idx: dict[str, SourcePacket],
) -> list[str]:
    """Map dropped claims' cited packets to a sorted, deduped list of panel names."""
    panels: set[str] = set()
    for i in dropped_claim_indexes:
        if i >= len(claims):
            continue
        for sid in claims[i].source_ids:
            pkt = pkt_idx.get(sid)
            if pkt is None:
                continue
            panel = _panel_for_packet(pkt)
            if panel:
                panels.add(panel)
    return sorted(panels)


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
