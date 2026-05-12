"""AgDR-0075 — unit tests for the critic LLM worker (Phase 6.1).

Covers the deterministic critic policy (used in eval mode + as the live-call
fallback), the safe-refusal rewrite of in-flight ``llm_output`` on reject,
the schema contract of ``CriticVerdict``, and the ``critic_node`` state
transitions. Live Anthropic calls are NOT exercised here — those are
covered by the graph_full eval cases under ``evals/cases/critic/``.
"""

from __future__ import annotations

import os

import pytest

# Match the pattern used by tests/integration/test_graph_happy_path.py:
# pin COPILOT_EVAL_MODE=1 BEFORE any app.* imports so the module-level
# ``_EVAL_MODE`` constant in app.graph.nodes is captured as True.
os.environ["COPILOT_EVAL_MODE"] = "1"

from app.graph.critic import (  # noqa: E402
    CRITIC_SAFE_REFUSAL_TEXT,
    apply_critic_verdict_to_llm_output,
    deterministic_critic_verdict,
)
from app.graph.nodes import critic_node  # noqa: E402
from app.schemas import CriticFlag, CriticVerdict  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _grounded_brief() -> dict[str, object]:
    return {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "A1c was 7.4% on 2026-01-15.",
                "claim_type": "fact",
                "source_ids": ["lab:a1c:jan"],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    }


def _a1c_packet() -> dict[str, object]:
    return {
        "source_id": "lab:a1c:jan",
        "patient_uuid": "uuid-A",
        "label": "A1c",
        "value": "7.4",
        "source_organization": None,
    }


def _acc_aha_packet() -> dict[str, object]:
    return {
        "source_id": "guideline:acc-aha:dose-titration:2025",
        "patient_uuid": "uuid-A",
        "label": "ACC/AHA cholesterol",
        "value": "Statin titration guidance",
        "source_organization": "ACC-AHA",
        "recommendation_grade": "B",
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestCriticVerdictSchema:
    def test_accepted_with_no_flags(self) -> None:
        v = CriticVerdict(accepted=True, flagged_claims=[], confidence=1.0)
        assert v.accepted is True
        assert v.flagged_claims == []
        assert v.confidence == 1.0

    def test_rejected_with_one_flag(self) -> None:
        v = CriticVerdict(
            accepted=False,
            flagged_claims=[CriticFlag(claim_index=0, reason="uncited", severity="reject")],
            confidence=0.9,
        )
        assert v.accepted is False
        assert v.flagged_claims[0].severity == "reject"

    def test_confidence_must_be_in_unit_range(self) -> None:
        with pytest.raises(Exception):
            CriticVerdict(accepted=True, flagged_claims=[], confidence=1.1)

    def test_claim_index_must_be_non_negative(self) -> None:
        with pytest.raises(Exception):
            CriticFlag(claim_index=-1, reason="x", severity="warn")


# ---------------------------------------------------------------------------
# Deterministic policy — happy path
# ---------------------------------------------------------------------------


class TestDeterministicCriticHappyPath:
    def test_grounded_fact_accepts(self) -> None:
        verdict = deterministic_critic_verdict(_grounded_brief(), [_a1c_packet()])
        assert verdict["accepted"] is True
        assert verdict["flagged_claims"] == []
        assert verdict["confidence"] == 1.0

    def test_refusal_brief_accepts_vacuously(self) -> None:
        brief = {
            "answer_type": "refusal",
            "claims": [],
            "missing_data": [],
            "refusals": ["out of scope"],
            "suggested_followups": [],
        }
        verdict = deterministic_critic_verdict(brief, [])
        assert verdict["accepted"] is True
        assert verdict["flagged_claims"] == []

    def test_empty_claims_accepts_vacuously(self) -> None:
        brief = dict(_grounded_brief())
        brief["claims"] = []
        verdict = deterministic_critic_verdict(brief, [])
        assert verdict["accepted"] is True


# ---------------------------------------------------------------------------
# Deterministic policy — reject paths
# ---------------------------------------------------------------------------


class TestDeterministicCriticRejectPaths:
    def test_empty_source_ids_rejects(self) -> None:
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Patient is at elevated cardiovascular risk.",
                    "claim_type": "fact",
                    "source_ids": [],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        verdict = deterministic_critic_verdict(brief, [_a1c_packet()])
        assert verdict["accepted"] is False
        rejects = [f for f in verdict["flagged_claims"] if f["severity"] == "reject"]
        assert len(rejects) == 1
        assert rejects[0]["claim_index"] == 0
        assert "no source_ids" in rejects[0]["reason"]

    def test_warfarin_dose_without_graded_citation_rejects(self) -> None:
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Increase warfarin to 7.5 mg daily.",
                    "claim_type": "fact",
                    "source_ids": ["lab:inr:apr"],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        packet = {
            "source_id": "lab:inr:apr",
            "patient_uuid": "uuid-A",
            "label": "INR",
            "value": "3.6",
            "source_organization": None,
        }
        verdict = deterministic_critic_verdict(brief, [packet])
        assert verdict["accepted"] is False
        rejects = [f for f in verdict["flagged_claims"] if f["severity"] == "reject"]
        assert len(rejects) == 1
        assert "dose change" in rejects[0]["reason"]

    def test_metformin_discontinuation_without_graded_citation_rejects(self) -> None:
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Discontinue metformin given recent eGFR trend.",
                    "claim_type": "fact",
                    "source_ids": ["lab:egfr:apr"],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        packet = {
            "source_id": "lab:egfr:apr",
            "patient_uuid": "uuid-A",
            "label": "eGFR",
            "value": "28",
            "source_organization": None,
        }
        verdict = deterministic_critic_verdict(brief, [packet])
        assert verdict["accepted"] is False
        assert any(
            f["severity"] == "reject" and "dose change" in f["reason"]
            for f in verdict["flagged_claims"]
        )

    def test_dose_change_with_acc_aha_citation_accepts(self) -> None:
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Consider titrating atorvastatin per ACC/AHA guidance.",
                    "claim_type": "fact",
                    "source_ids": ["guideline:acc-aha:dose-titration:2025"],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        verdict = deterministic_critic_verdict(brief, [_acc_aha_packet()])
        assert verdict["accepted"] is True


# ---------------------------------------------------------------------------
# Deterministic policy — warn-only paths
# ---------------------------------------------------------------------------


class TestDeterministicCriticWarnPaths:
    def test_unresolved_citation_warns_but_accepts(self) -> None:
        """A claim whose source_ids point to a packet that's not present
        is a 'warn' (the verifier's source_attribution rule will drop it).
        Critic should not reject — that's verifier territory."""
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Active problem: HTN.",
                    "claim_type": "fact",
                    "source_ids": ["problem:fabricated:99"],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        verdict = deterministic_critic_verdict(brief, [_a1c_packet()])
        assert verdict["accepted"] is True
        warns = [f for f in verdict["flagged_claims"] if f["severity"] == "warn"]
        assert len(warns) == 1
        assert warns[0]["claim_index"] == 0


# ---------------------------------------------------------------------------
# Safe-refusal rewrite
# ---------------------------------------------------------------------------


class TestApplyCriticVerdict:
    def test_accept_passes_through_unchanged(self) -> None:
        brief = _grounded_brief()
        verdict = {"accepted": True, "flagged_claims": [], "confidence": 1.0}
        result = apply_critic_verdict_to_llm_output(brief, verdict)
        assert result == brief

    def test_warn_only_passes_through_unchanged(self) -> None:
        brief = _grounded_brief()
        verdict = {
            "accepted": True,
            "flagged_claims": [
                {"claim_index": 0, "reason": "warn", "severity": "warn"}
            ],
            "confidence": 0.8,
        }
        result = apply_critic_verdict_to_llm_output(brief, verdict)
        assert result == brief

    def test_reject_rewrites_to_safe_refusal(self) -> None:
        brief = _grounded_brief()
        verdict = {
            "accepted": False,
            "flagged_claims": [
                {"claim_index": 0, "reason": "uncited", "severity": "reject"}
            ],
            "confidence": 0.9,
        }
        result = apply_critic_verdict_to_llm_output(brief, verdict)
        assert result["answer_type"] == "refusal"
        assert result["claims"] == []
        assert result["refusals"] == [CRITIC_SAFE_REFUSAL_TEXT]

    def test_not_accepted_but_no_reject_flags_passes_through(self) -> None:
        """Defensive: ``accepted=False`` with only warn flags should not
        trigger the safe-refusal rewrite. The reject severity is what
        gates the rewrite, not the boolean alone."""
        brief = _grounded_brief()
        verdict = {
            "accepted": False,
            "flagged_claims": [
                {"claim_index": 0, "reason": "warn", "severity": "warn"}
            ],
            "confidence": 0.6,
        }
        result = apply_critic_verdict_to_llm_output(brief, verdict)
        assert result == brief


# ---------------------------------------------------------------------------
# critic_node integration (in eval mode — no Anthropic call)
# ---------------------------------------------------------------------------


class TestCriticNodeEvalMode:
    """End-to-end critic_node invocation under COPILOT_EVAL_MODE=1."""

    def test_critic_node_accepts_grounded_brief(self) -> None:
        state = {
            "llm_output": _grounded_brief(),
            "extracted_packets": [_a1c_packet()],
            "guideline_packets": [],
            "question": "What is the latest A1c?",
            "current_node": "synthesizer",
            "graph_path": ["synthesizer"],
            "worker_handoffs": [],
        }
        result = critic_node(state)
        assert result["critic_status"] == "passed"
        assert result["critic_verdict"]["accepted"] is True
        assert "critic" in result["graph_path"]
        assert result["llm_output"] == state["llm_output"]

    def test_critic_node_rejects_uncited_claim_and_rewrites_llm_output(self) -> None:
        brief = {
            "answer_type": "pre_room_brief",
            "claims": [
                {
                    "text": "Patient is at elevated cardiovascular risk.",
                    "claim_type": "fact",
                    "source_ids": [],
                    "caveat": None,
                }
            ],
            "missing_data": [],
            "refusals": [],
            "suggested_followups": [],
        }
        state = {
            "llm_output": brief,
            "extracted_packets": [_a1c_packet()],
            "guideline_packets": [],
            "question": "Should we worry about this patient?",
            "current_node": "synthesizer",
            "graph_path": ["synthesizer"],
            "worker_handoffs": [],
        }
        result = critic_node(state)
        assert result["critic_status"] == "rejected"
        assert result["critic_verdict"]["accepted"] is False
        # llm_output rewritten to safe-refusal
        assert result["llm_output"]["answer_type"] == "refusal"
        assert result["llm_output"]["claims"] == []
        assert result["llm_output"]["refusals"] == [CRITIC_SAFE_REFUSAL_TEXT]

    def test_critic_node_skips_existing_refusal(self) -> None:
        brief = {
            "answer_type": "refusal",
            "claims": [],
            "missing_data": [],
            "refusals": ["Already refused upstream."],
            "suggested_followups": [],
        }
        state = {
            "llm_output": brief,
            "extracted_packets": [],
            "guideline_packets": [],
            "question": "Some question",
            "current_node": "synthesizer",
            "graph_path": ["synthesizer"],
            "worker_handoffs": [],
        }
        result = critic_node(state)
        assert result["critic_status"] == "skipped"
        assert result["llm_output"] == brief
