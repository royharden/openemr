"""L1: Clinical-synonym query rewriter (AgDR-0085, Plan §7.2.c).

Three layers under test:
  1. ``app.rag.synonyms.variants_for`` — flat lookup table; case-insensitive.
  2. ``app.rag.query_rewriter.expand_query`` — generates up-to-N paraphrases
     by single-token substitution; preserves the original at position 0.
  3. ``app.rag.query_rewriter.should_use_llm_fallback`` — heuristic for
     when the deterministic expander runs dry and the LLM-paraphrase pass
     would help (Wk3 feature; the flag is exposed but no caller passes a
     real LLM in Wk2).

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

from app.rag.query_rewriter import (
    LLM_FALLBACK_WORD_THRESHOLD,
    MAX_PARAPHRASES,
    expand_query,
    expand_query_with_llm_fallback,
    should_use_llm_fallback,
)
from app.rag.synonyms import variants_for


# ---------------------------------------------------------------------------
# variants_for (positive / negative / edge)
# ---------------------------------------------------------------------------


class TestSynonymsLookupPositive:
    def test_a1c_returns_full_group(self) -> None:
        v = variants_for("A1c")
        assert v is not None
        for expected in ("a1c", "hba1c", "hemoglobin a1c", "glycated hemoglobin"):
            assert expected in v, f"missing {expected!r} in A1c variants"

    def test_brand_to_generic_pair(self) -> None:
        v = variants_for("Lipitor")
        assert v is not None
        assert "atorvastatin" in v
        assert "lipitor" in v

    def test_generic_to_brand_pair(self) -> None:
        v = variants_for("warfarin")
        assert v is not None
        assert "coumadin" in v

    def test_case_insensitive(self) -> None:
        assert variants_for("HBA1C") == variants_for("hba1c")
        assert variants_for("METFORMIN") == variants_for("metformin")


class TestSynonymsLookupNegative:
    def test_unknown_token_returns_none(self) -> None:
        assert variants_for("xylophone") is None

    def test_empty_token_returns_none(self) -> None:
        assert variants_for("") is None


# ---------------------------------------------------------------------------
# expand_query (positive / negative / edge)
# ---------------------------------------------------------------------------


class TestExpandQueryPositive:
    def test_original_query_always_first(self) -> None:
        original = "Is her A1c controlled?"
        out = expand_query(original)
        assert out[0] == original

    def test_a1c_expansion_includes_hba1c(self) -> None:
        """Plan §7.2.c bug-this-catches: 'Is her A1c controlled?' must
        produce a paraphrase using 'HbA1c' or 'hemoglobin A1c' so BM25
        finds chunks that use the alternative spelling."""
        out = expand_query("Is her A1c controlled?")
        flattened = " ".join(out).lower()
        assert "hba1c" in flattened or "hemoglobin a1c" in flattened or "glycated" in flattened

    def test_drug_brand_expansion(self) -> None:
        """Lipitor → atorvastatin (and back) — brand/generic pair."""
        out = expand_query("Is Lipitor working for him?")
        flattened = " ".join(out).lower()
        assert "atorvastatin" in flattened

    def test_multiple_synonym_tokens_in_one_query(self) -> None:
        """A query with TWO synonymable tokens (HbA1c + warfarin) should
        produce paraphrases that swap each independently."""
        out = expand_query("Is her A1c affected by warfarin dosing?")
        flattened = " ".join(out).lower()
        # At least one paraphrase swaps A1c, at least one swaps warfarin.
        assert any(("hba1c" in p.lower() or "hemoglobin" in p.lower() or "glycated" in p.lower()) for p in out[1:])
        assert any("coumadin" in p.lower() for p in out[1:])


class TestExpandQueryNegative:
    def test_unknown_terms_yield_only_original(self) -> None:
        out = expand_query("xylophone zither piccolo")
        assert out == ["xylophone zither piccolo"]

    def test_empty_query_returns_singleton_empty(self) -> None:
        assert expand_query("") == [""]

    def test_punctuation_only_returns_singleton(self) -> None:
        assert expand_query("?!?") == ["?!?"]


class TestExpandQueryEdge:
    def test_cap_at_max_paraphrases(self) -> None:
        """A query with many synonymable tokens caps at MAX_PARAPHRASES."""
        out = expand_query("HbA1c LDL HDL TG eGFR creatinine TSH BP")
        assert len(out) <= MAX_PARAPHRASES

    def test_caller_can_lower_cap(self) -> None:
        out = expand_query("Is her A1c controlled?", max_paraphrases=2)
        assert len(out) <= 2

    def test_zero_cap_clamped_to_one(self) -> None:
        """The cap is clamped to 1 so the original is always returned."""
        out = expand_query("anything", max_paraphrases=0)
        assert out == ["anything"]

    def test_no_duplicates_in_output(self) -> None:
        """Multiple substitutions that yield the same paraphrase are deduped."""
        out = expand_query("Is her HbA1c HbA1c HbA1c controlled?")
        assert len(out) == len(set(p.lower() for p in out))

    def test_punctuation_preserved_around_substitution(self) -> None:
        """The substitution must not eat surrounding punctuation."""
        out = expand_query("Is her A1c (most recent) controlled?")
        # At least one paraphrase preserves the parens.
        assert any("(" in p and ")" in p for p in out)


# ---------------------------------------------------------------------------
# should_use_llm_fallback (positive / negative)
# ---------------------------------------------------------------------------


class TestLlmFallbackHeuristic:
    def test_long_query_triggers_fallback(self) -> None:
        long_q = " ".join(["word"] * (LLM_FALLBACK_WORD_THRESHOLD + 1))
        assert should_use_llm_fallback(long_q) is True

    def test_short_query_with_synonym_does_not_trigger(self) -> None:
        assert should_use_llm_fallback("Check her A1c") is False

    def test_zero_synonym_hits_triggers_fallback(self) -> None:
        """Even a short query with no synonym hits should trigger fallback —
        the deterministic expander has nothing to add."""
        assert should_use_llm_fallback("xylophone zither") is True


# ---------------------------------------------------------------------------
# expand_query_with_llm_fallback (positive / negative)
# ---------------------------------------------------------------------------


class TestLlmFallbackWiring:
    def test_returns_deterministic_when_no_llm_provided(self) -> None:
        """No llm_paraphraser → degrades to expand_query() exactly."""
        deterministic = expand_query("Is her A1c controlled?")
        out = expand_query_with_llm_fallback("Is her A1c controlled?")
        assert out == deterministic

    def test_llm_extras_appended_when_heuristic_fires(self) -> None:
        long_q = " ".join(["word"] * (LLM_FALLBACK_WORD_THRESHOLD + 1))
        called: dict[str, int] = {"n": 0}

        def fake_llm(q: str) -> list[str]:
            called["n"] += 1
            return ["paraphrase from llm one", "paraphrase from llm two"]

        out = expand_query_with_llm_fallback(long_q, llm_paraphraser=fake_llm)
        assert called["n"] == 1
        assert "paraphrase from llm one" in out

    def test_llm_failure_falls_back_to_deterministic(self) -> None:
        """When the LLM raises, we don't crash — we return what we had."""
        def boom(q: str) -> list[str]:
            raise RuntimeError("simulated vendor outage")

        long_q = " ".join(["word"] * (LLM_FALLBACK_WORD_THRESHOLD + 1))
        out = expand_query_with_llm_fallback(long_q, llm_paraphraser=boom)
        # Did not crash; returned at least the original.
        assert out[0] == long_q
