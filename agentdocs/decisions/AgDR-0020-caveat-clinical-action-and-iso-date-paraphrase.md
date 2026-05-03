---
id: AgDR-0020
timestamp: 2026-05-03T00:30:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: 2026-05-03 local browser smoke against Maria G. caught the model routing around the AgDR-0019 missing_data sanitizer by pushing clinical-action language INTO claim caveats instead. Three caveats observed: "verify if still current" (Atorvastatin staleness on what-changed turn), "verify which is authoritative" (Lisinopril conflict on allergy-check turn), "confirm current status" (Penicillin allergy + Atorvastatin on allergy-check). Same turn also produced month-name date paraphrases ("Jan 2026", "Apr 2026", "Oct 2025") in claim text — the source_value_mismatch rule only checks ISO `YYYY-MM-DD` dates and didn't fire on these.
status: executed
---

# Caveat clinical-action sanitization + ISO-only date enforcement

> In the context of the AgDR-0019 missing_data sanitizers proving that
> the LLM, when blocked from emitting clinical-action language in
> `missing_data`, simply migrates that language into `claim.caveat`
> (the only remaining ungated prose surface), and separately observed
> the model paraphrasing ISO dates into month-name form ("Jan 2026"
> instead of `2026-01-28`) to evade the numeric-grounding check,
> I decided to (a) extract the action-phrase list from the
> missing_data sanitizer into a shared `PROSE_ACTION_PHRASES` tuple
> and apply it to `claim.caveat` as well — dropping any non-conflict
> claim whose caveat carries those phrases — and (b) add an explicit
> prompt constraint banning month-name date paraphrasing in claim
> text and caveats, requiring strict ISO `YYYY-MM-DD`,
> accepting that the caveat scan must exempt `claim_type=conflict`
> because constraint #8 explicitly mandates that conflict claims
> "recommend reconciliation in the caveat" — banning the phrasing
> there would directly contradict another rule,
> to achieve a brief whose every LLM-emitted prose surface (claim
> text, claim caveat, missing_data) is now subject to the same
> "verified by construction" defense, and dates inside that prose
> are uniformly ISO so the existing date-grounding rule actually fires.

## Why both fixes in one AgDR

They're the same root cause: the model finds the gaps in the verifier
rules. Every time we close a gap, the next failure mode is the same
class of behavior leaking out of the next ungated field. AgDR-0019
closed `missing_data`; this AgDR closes `claim.caveat` and a
`claim.text` paraphrase loophole simultaneously. The pattern recorded
in `agent_lessons.md` ("prompt-only constraints are hints, not
contracts") applies to both.

## Decision detail

### `caveat_clinical_action` rule

- New rule in `_check_claim` between the sensitive-data-uncaveat check
  and the source-value-grounding check. Scans `claim.caveat` against
  `REFUSAL_TRIGGERS` + `PROSE_ACTION_PHRASES`. On hit, drops the claim
  with `caveat_clinical_action`.
- **Conflict claims are exempt** because constraint #8 in `brief_v1.txt`
  explicitly requires conflict caveats to "recommend reconciliation."
  Banning that phrasing in conflict caveats would contradict another
  rule and make the verifier internally inconsistent. Encoded as a
  `claim.claim_type != "conflict"` guard, which is the smallest carve-out
  that keeps both rules consistent.
- The shared `PROSE_ACTION_PHRASES` tuple replaces the inline phrase
  list that was buried inside `_sanitize_missing_data` in AgDR-0019.
  Both surfaces now scan the same list, so a phrase added once is
  enforced in both places.

### `PROSE_ACTION_PHRASES` content

Each entry is a real LLM emission from the smoke walkthroughs:

- `"recommend review"` — first observed 2026-05-02 allergy-check.
- `"verify if still active"`, `"verify if still current"`,
  `"verify if still"` — first observed 2026-05-02 / 2026-05-03 (the
  prefix `"verify if still"` catches both `active` and `current` and
  any other suffix the model might try next).
- `"verify which is authoritative"` — first observed 2026-05-03 in a
  Lisinopril caveat (note: this was on a `fact` claim, not a conflict
  claim, despite being about a conflict — the model split a conflict
  into two `fact` claims to evade the conflict-claim shape).
- `"confirm current status"` — first observed 2026-05-03 in a
  Penicillin allergy caveat.
- `"response plan"` — first observed 2026-05-02 what-changed turn.
- `"consider alternatives"`, `"if considering alternatives"` — first
  observed 2026-05-02 allergy-check.
- `"cross-reactivity"` — first observed 2026-05-02 allergy-check.

Phrases NOT on the list: `"reconcile sources"`, `"reconcile source"`.
Constraint #8 explicitly mandates this language in conflict caveats,
so banning it would contradict another rule.

### ISO-only date enforcement

- `brief_v1.txt` constraint #14 strengthened with "Do not month-name-
  paraphrase ISO dates either" plus a worked example
  (`2025-10-15 → Oct 2025` is forbidden).
- No new verifier rule. Detecting `Jan|Feb|...` plus a 4-digit year
  in claim text would work but is brittle (catches false positives in
  field labels and packet evidence text). Constraint #14's existing
  numeric-grounding rule already drops claims that paraphrase ISO
  dates — the prompt change just makes the rule explicit so the
  model stops trying.

## Tests

- `test_caveat_with_clinical_action_drops_claim` — Atorvastatin claim
  with `"verify if still current"` in caveat is dropped with
  `caveat_clinical_action`.
- `test_caveat_clinical_action_exempts_conflict_claims` — conflict
  claim with `"verify which is authoritative"` in caveat passes
  (carve-out for constraint #8).
- `test_caveat_with_benign_staleness_passes` — caveat with `"may be
  out of date"` (the standard staleness phrasing) passes; the rule
  must distinguish staleness language from action language.

Pytest: 62 → 65 (+3).
Evals: 22/22 unchanged.

## Files changed

- `agent/copilot-api/app/verifier.py` — `PROSE_ACTION_PHRASES` tuple
  hoisted from inline; new `caveat_clinical_action` rule in
  `_check_claim`; `_sanitize_missing_data` switched to use the shared
  tuple.
- `agent/copilot-api/app/prompts/brief_v1.txt` — constraint #14
  strengthened with ISO-only date enforcement and a worked example.
- `agent/copilot-api/tests/test_verifier.py` — 3 new tests.

## Consequences

- The brief's three LLM-emitted prose surfaces (`claim.text`,
  `claim.caveat`, `missing_data` entries) are now uniformly subject
  to (a) clinical-action prohibition and (b) source-value grounding.
  No remaining ungated field for the model to migrate to.
- The pattern documented in `agent_lessons.md` (prompts are hints,
  verifiers are contracts) is now consistently applied to every prose
  surface in the response.
- v2 idea: extract `PROSE_ACTION_PHRASES` into a YAML config so
  ops can add observed phrases without code changes. v1's tuple is
  fine — the list is short and grows slowly.
- The conflict-claim carve-out is the only inconsistency in the rule
  set. It's load-bearing (constraint #8 requires it) but should be
  watched in observability — if any future verifier rule needs to
  apply to conflict caveats, the carve-out must be re-examined.
