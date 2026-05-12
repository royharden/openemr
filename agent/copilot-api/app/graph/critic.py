"""Critic LLM worker — AgDR-0075, Phase 6.1.

The critic runs between ``synthesizer_node`` and ``verifier_node`` to catch
unsafe suggestions the deterministic verifier rules can't enumerate (medication
dose changes without grade-B+ citations, claims with unrelated citations,
escalation language that has no source). On any ``severity="reject"`` flag the
critic rewrites the in-flight ``llm_output`` to a safe-refusal shape so the
verifier sees a clean refusal rather than a flagged-but-still-claiming brief.

In ``COPILOT_EVAL_MODE=1`` the LLM call is replaced by a deterministic
keyword + citation-grade rule that mirrors the live prompt's logic. The same
rule is used as the offline fallback when the live Anthropic call fails or
the structured-output schema doesn't validate after one repair attempt — the
critic is a safety net, so degrading to deterministic rules is preferable to
silently passing every brief through.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

CRITIC_TOOL_NAME = "emit_critic_verdict"

# Patterns whose presence in a claim's text triggers the "medication
# dose-change / discontinuation / escalation" guardrail. The set is a
# closed enumeration — extending it requires a unit-test update and a
# new AgDR.
#
# Branches:
#   1. Dose-change verbs: escalate, titrate, discontinue, taper, stop X.
#   2. "increase/decrease <drug> to <N>" — the canonical dose-change phrase
#      ("Increase warfarin to 7.5 mg") doesn't always say the word "dose".
#   3. "increase/decrease the dose|dosing|dosage" — phrase form.
#   4. "start <drug> at <N>" / "switch to <drug>" / "add <drug> <N> mg".
#   5. "<N> mg <frequency>" where frequency is a clinical abbreviation OR
#      "daily" / "twice daily" / "once daily" / "weekly" etc.
_DOSE_CHANGE_RE = re.compile(
    r"\b("
    r"escalat\w*|titrat\w*|discontinu\w*|taper\w*|stop\s+\w+|"
    r"increase\s+\S+\s+to\s+\d|decrease\s+\S+\s+to\s+\d|"
    r"increase\s+(?:the\s+)?(?:dose|dosing|dosage)|"
    r"decrease\s+(?:the\s+)?(?:dose|dosing|dosage)|"
    r"start\s+\S+\s+(?:at|on)\s+\d|switch\s+to\s+\S+|"
    r"add\s+\S+\s+\d+\s*mg|"
    r"\d+\s*mg\s+(?:bid|tid|qhs|qd|qod|prn|po|iv|im|sc|sublingual|daily|weekly|nightly)"
    r")\b",
    re.IGNORECASE,
)

# Source-organization strings that satisfy "graded clinical citation" for
# the dose-change / discontinuation / escalation guardrail. Anything else
# (a lab packet, a problem-list entry, a sensitive-encounter row, a
# non-graded guideline chunk) is insufficient.
_GRADED_CITATION_SOURCES = frozenset({"ACC-AHA", "ADA", "FDA", "CDC-ACIP"})


def critic_verdict_tool() -> dict[str, Any]:
    """Forced tool schema for the live Anthropic critic call.

    Mirrors ``app/extractors/anthropic_tools.py`` shape so the parsing path
    is symmetrical with the existing extractors. The schema is published
    via ``model_json_schema()`` rather than hand-rolled so a future
    rename of ``CriticFlag`` / ``CriticVerdict`` doesn't drift here.
    """

    from app.schemas import CriticVerdict

    return {
        "name": CRITIC_TOOL_NAME,
        "description": (
            "Emit the critic verdict over the synthesized brief. For each "
            "claim, decide whether at least one cited source packet plausibly "
            "supports the claim. Flag any claim that proposes a medication "
            "dose change, discontinuation, or escalation without a grade-B+ "
            "citation from ACC/AHA, ADA, FDA, or a grade-A ACIP source."
        ),
        "input_schema": CriticVerdict.model_json_schema(),
    }


def deterministic_critic_verdict(
    llm_output: dict[str, Any],
    packets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the critic's policy as a pure function — used in eval mode and
    as the live-failure fallback.

    Policy:
    - Skip critic entirely for refusals (no claims to evaluate).
    - For each claim, if ``source_ids`` is empty → REJECT (uncited claim).
    - For each claim, if any cited source_id is NOT in the packet set →
      WARN (unrelated/fabricated citation — verifier will also drop it via
      ``source_attribution`` but the critic gives the user-visible reason).
    - For each claim whose text matches ``_DOSE_CHANGE_RE`` (medication
      dose change / discontinuation / escalation), require at least one
      cited source whose ``source_organization`` is in
      ``_GRADED_CITATION_SOURCES``. Otherwise → REJECT.
    - ``accepted = True`` iff zero reject-severity flags. Warn-only flags
      are non-fatal.
    - ``confidence = 1.0`` in deterministic mode — the rules are
      side-effect-free and reproducible.
    """

    claims = llm_output.get("claims") or []
    answer_type = llm_output.get("answer_type", "pre_room_brief")

    # Refusals carry no claims to evaluate; the safe-refusal short-circuit
    # downstream of critic_node is for *this* node's reject path, not for
    # an already-refused brief. Pass through cleanly.
    if answer_type == "refusal" or not claims:
        return {
            "accepted": True,
            "flagged_claims": [],
            "confidence": 1.0,
        }

    packets_by_id: dict[str, dict[str, Any]] = {}
    for p in packets:
        if not isinstance(p, dict):
            continue
        sid = p.get("source_id")
        if isinstance(sid, str) and sid:
            packets_by_id[sid] = p

    flags: list[dict[str, Any]] = []

    for idx, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("text") or "")
        cited_ids = [s for s in (claim.get("source_ids") or []) if isinstance(s, str)]
        cited_packets = [packets_by_id[s] for s in cited_ids if s in packets_by_id]

        if not cited_ids:
            flags.append({
                "claim_index": idx,
                "reason": "Claim has no source_ids — critic cannot verify against any retrieved source.",
                "severity": "reject",
            })
            continue

        unresolved = [s for s in cited_ids if s not in packets_by_id]
        if unresolved:
            flags.append({
                "claim_index": idx,
                "reason": (
                    "Cited source(s) "
                    + ", ".join(sorted(unresolved)[:3])
                    + " are not in the retrieved packet set."
                ),
                "severity": "warn",
            })

        if _DOSE_CHANGE_RE.search(text):
            has_graded = any(
                str(p.get("source_organization") or "") in _GRADED_CITATION_SOURCES
                for p in cited_packets
            )
            if not has_graded:
                flags.append({
                    "claim_index": idx,
                    "reason": (
                        "Suggestion involves a medication dose change, "
                        "discontinuation, or escalation but no grade-B+ "
                        "citation from ACC/AHA, ADA, FDA, or grade-A ACIP "
                        "is present in the retrieved sources."
                    ),
                    "severity": "reject",
                })

    accepted = not any(f["severity"] == "reject" for f in flags)
    return {
        "accepted": accepted,
        "flagged_claims": flags,
        "confidence": 1.0,
    }


def _call_live_critic(
    llm_output: dict[str, Any],
    packets: list[dict[str, Any]],
    question: str,
) -> dict[str, Any]:
    """Live Anthropic call. Forced tool-use mirroring the synthesizer pattern.

    Falls back to ``deterministic_critic_verdict`` on any failure (invalid
    schema after one repair, network error, missing API key). The critic
    is a safety net — degrading to a deterministic rule is strictly safer
    than crashing the request.
    """

    try:
        import anthropic  # type: ignore[import-not-found]
        from app.schemas import CriticVerdict
    except ImportError:
        logger.warning("critic: anthropic SDK unavailable; using deterministic fallback")
        return deterministic_critic_verdict(llm_output, packets)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("critic: ANTHROPIC_API_KEY missing; using deterministic fallback")
        return deterministic_critic_verdict(llm_output, packets)

    model = os.getenv("COPILOT_CRITIC_MODEL", "claude-haiku-4-5-20251001")
    client = anthropic.Anthropic(api_key=api_key)

    # Compact prompt — critic sees the brief's claims and a packet summary
    # only (no extended context). The deterministic policy doubles as the
    # rubric the LLM is asked to follow.
    system_prompt = (
        "You are a clinical safety critic. For each claim in the synthesized "
        "brief, decide whether at least one cited source packet plausibly "
        "supports the claim. Flag any claim that proposes a medication dose "
        "change, discontinuation, or escalation without a grade-B+ citation "
        "from ACC/AHA, ADA, FDA, or a grade-A ACIP source. "
        f"Use the {CRITIC_TOOL_NAME} tool. Confidence is your subjective "
        "estimate in [0, 1]. Use claim_index for the zero-based position of "
        "the claim in the input list."
    )

    payload = {
        "question": question[:500],
        "claims": llm_output.get("claims", []),
        "packets": [
            {
                "source_id": p.get("source_id"),
                "source_organization": p.get("source_organization"),
                "recommendation_grade": p.get("recommendation_grade"),
                "label": p.get("label"),
                "quote_or_value": (str(p.get("quote_or_value") or "")[:200] or None),
                "value": p.get("value"),
            }
            for p in packets[:30]
            if isinstance(p, dict)
        ],
    }

    def _create(prompt: str) -> Any:
        return client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            tools=[critic_verdict_tool()],
            tool_choice={"type": "tool", "name": CRITIC_TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )

    def _parse(response: Any) -> tuple[dict[str, Any] | None, list[str]]:
        tool_input: dict[str, Any] | None = None
        raw_text = ""
        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                raw_text += str(getattr(block, "text", ""))
            elif block_type == "tool_use" and getattr(block, "name", None) == CRITIC_TOOL_NAME:
                candidate = getattr(block, "input", None)
                if isinstance(candidate, dict):
                    tool_input = candidate
        if tool_input is None:
            return None, [f"missing {CRITIC_TOOL_NAME} tool call"]
        try:
            validated = CriticVerdict.model_validate(tool_input).model_dump()
            return validated, []
        except Exception as exc:
            return None, [f"CriticVerdict schema validation failed: {exc}"]

    user_msg = "Brief to critique:\n" + json.dumps(payload, default=str)

    try:
        response = _create(user_msg)
    except Exception as exc:
        logger.warning("critic: live call failed (%s); using deterministic fallback", exc)
        return deterministic_critic_verdict(llm_output, packets)

    parsed, errors = _parse(response)
    if parsed is not None:
        return parsed

    logger.info("critic: retrying after invalid tool payload: %s", "; ".join(errors))
    try:
        repair_response = _create(
            "Your previous response failed structured validation:\n- "
            + "\n- ".join(errors[:3])
            + "\nReturn a corrected verdict using the tool.\n\n"
            + user_msg
        )
    except Exception as exc:
        logger.warning("critic: repair call failed (%s); using deterministic fallback", exc)
        return deterministic_critic_verdict(llm_output, packets)

    repaired, repair_errors = _parse(repair_response)
    if repaired is not None:
        return repaired

    logger.warning(
        "critic: structured output failed twice (%s); using deterministic fallback",
        "; ".join(repair_errors or errors),
    )
    return deterministic_critic_verdict(llm_output, packets)


# Safe-refusal payload used when the critic rejects. The exact wording is
# pinned by the eval cases — changing it requires updating
# ``evals/cases/critic/critic_*.json`` and the unit tests.
CRITIC_SAFE_REFUSAL_TEXT = (
    "The Co-Pilot's draft answer included a claim the critic could not "
    "verify against the retrieved sources. The original draft is hidden; "
    "please ask a more specific question or upload supporting documentation."
)


def apply_critic_verdict_to_llm_output(
    llm_output: dict[str, Any],
    verdict: dict[str, Any],
) -> dict[str, Any]:
    """Return the (possibly rewritten) llm_output after applying the verdict.

    On reject → safe-refusal shape (answer_type="refusal", claims=[],
    refusals=[CRITIC_SAFE_REFUSAL_TEXT]). The original draft is intentionally
    NOT preserved in the response — the developer-only debug surface in
    Langfuse (recorded via the critic_node span) carries the flagged claim
    list for post-hoc inspection.

    On warn / accept → pass through unchanged. The per-claim flag metadata
    rides on the ``critic_verdict`` field of ``VerifiedResponse``; the UI
    consults it to render an amber "uncertain" badge.
    """

    if verdict.get("accepted"):
        return llm_output

    flagged = verdict.get("flagged_claims") or []
    has_reject = any(
        isinstance(f, dict) and f.get("severity") == "reject"
        for f in flagged
    )
    if not has_reject:
        return llm_output

    return {
        "answer_type": "refusal",
        "claims": [],
        "missing_data": list(llm_output.get("missing_data") or []),
        "refusals": [CRITIC_SAFE_REFUSAL_TEXT],
        "suggested_followups": list(llm_output.get("suggested_followups") or []),
    }
