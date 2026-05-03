---
id: AgDR-0014
timestamp: 2026-05-02T19:10:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Slice B of plan_next02_opus47_2026-05-02_remediation_and_submission.md, in response to a codex audit finding that the deterministic verifier checks citation existence but never compares claim-text values against cited packet values.
status: executed
---

# Source-value grounding rule in the deterministic verifier

> In the context of every clinical claim being source-cited but the cited
> values being trusted blindly,
> I decided to add a `source_value_mismatch` verifier rule that requires every
> explicit number and ISO date in claim text to appear verbatim in at least
> one cited packet's evidence string,
> accepting that the rule is intentionally narrow (numbers + dates only — no
> free-prose synonym overlap) and may produce false negatives for paraphrased
> medical language,
> to achieve a verifier that catches the load-bearing failure mode (a `100 mg`
> claim citing a `10 mg` packet) without false-positive drops on legitimate
> synonym usage like `elevated`/`high`/`abnormal`.

## Decision detail

- New rule fires for `claim_type in {fact, trend, conflict}`. Skips `absence`
  because absence claims rarely carry packet values.
- Number extraction uses a strict word-boundary regex that ignores digits glued
  to letters (so `5` inside `rx:prescriptions:5` and `23` inside `PPSV23` do
  not count as claim numbers). Source IDs are also stripped from the claim
  text before extraction.
- Numeric equivalence: `10` matches `10` and `10.0`; `10.0` matches `10`.
  `10` does NOT match `100` (the canonical probe).
- Date matching is exact ISO `YYYY-MM-DD` substring match against the
  concatenated evidence text from each cited packet.
- Evidence text per packet = lowercase NFKC normalization of `label`, `value`,
  `unit`, `observed_at`, `last_updated`, `status`, `field`, dash-normalized,
  whitespace-collapsed.
- Prompt addendum (`prompts/brief_v1.txt` constraint #14) tells the LLM
  explicitly: every number and ISO date in claim text must appear verbatim in
  at least one cited packet. This reduces drop rate at runtime so
  `unsupported_dropped` doesn't inflate every turn.

## Why narrow on numbers + dates only (deferring prose-token overlap)

The codex plan also proposed a "condition fact requires clinical-token overlap"
rule (e.g. claim `Active hypertension` must overlap a packet whose value
contains `hypertension`). I deferred this to v2 because:

1. **Synonym false-positive risk is high.** Lab abnormality language varies
   (`elevated`, `high`, `abnormal`, `out of range`, `flagged`). Any token
   overlap rule would either be too loose (everything matches) or too strict
   (drop legitimate synonyms).
2. **Numbers and dates carry the highest patient-safety risk.** A wrong dose
   or a wrong date is a directly actionable mistake; a paraphrased problem
   name usually isn't.
3. **The deferred rule does not weaken v1's defense story.** The prompt
   addendum + the citation-existence + patient-binding + active-status
   rules already block fabricated problem claims; what they didn't catch
   was wrong values within real citations.

## Tests + evals

- 9 new pytest cases in `tests/test_verifier.py` covering med-dose
  mismatch/match, lab-value mismatch/match, decimal equivalence, observed-date
  mismatch, trend-with-uncited-value, source-id-number stripping, and
  absence-skip. One existing trend test was repaired (it had an incidental
  ungrounded `16 mo` in its claim text — the new rule correctly caught it,
  proving the rule works as advertised).
- 4 new eval cases (19–22) covering the canonical mismatch probes (med dose,
  lab value, trend, observed date). Eval count: 22/22.
- Pytest count after Slice B: 50/50 (was 41/41).

## Files changed

- `agent/copilot-api/app/verifier.py` — `_check_source_value_grounding`,
  helpers, and rule wiring inside `_check_claim`.
- `agent/copilot-api/app/prompts/brief_v1.txt` — constraint #14 added.
- `agent/copilot-api/tests/test_verifier.py` — 9 new tests; trend fixture
  repaired.
- `agent/copilot-api/evals/cases/19..22_value_mismatch_*.json` — 4 new cases.

## Consequences

- Future agents tweaking the verifier should resist adding prose-overlap
  rules without an explicit eval suite for synonyms; the v2 follow-up
  is to gather a corpus of real synonym phrases from production traces
  before designing that rule.
- The prompt addendum + verifier rule are belt-and-suspenders: dropping
  one without the other re-introduces the failure mode in different shapes.
- A claim citing the right packet but writing the wrong number is now
  the visible failure mode in `verifier_issues`, which is a concrete
  defensibility win for the demo.
