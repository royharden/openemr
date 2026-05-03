---
id: AgDR-0019
timestamp: 2026-05-02T23:30:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: 2026-05-02 ~22:50Z local browser smoke against Maria G. (after restarting uvicorn so the prompt change in AgDR-0018 was loaded). Even with constraint #15 ("missing_data honesty") in the prompt, the model still hallucinated `"Immunization status beyond Hepatitis A (last dose 2019-10-12) — current status for influenza, tetanus, COVID-19, and other age-appropriate vaccines not documented in supplied packets"` against a chart whose only immunization packet is Pneumococcal PPSV23 (CVX 33). The on-loadup brief also surfaced `"Reason for A1c rise and response plan"` and the allergy-check turn surfaced `"verify if still active"` / `"recommend review for cross-reactivity with beta-lactams if considering alternatives"` — all in `missing_data` prose, all bypassing the deterministic verifier because no rule gated that field.
status: executed
---

# Verifier deterministically sanitizes `missing_data` prose

> In the context of `missing_data` being free LLM prose without any
> verifier gate — leaving the door open for hallucinated entity names
> and clinical recommendations that bypass every defense the brief
> otherwise has —
> I decided to add two deterministic verifier rules
> (`missing_data_clinical_action` and `missing_data_named_entity`),
> extend `source_value_mismatch` to also check `claim.caveat` for ISO
> dates, and surface an explicit "no verified claims could be produced
> for this turn" line when every candidate claim was dropped,
> accepting that the named-entity rule uses a small static keyword list
> rather than a true clinical vocabulary (so it will miss novel drug
> names but catch the high-frequency hallucination classes seen in
> smoke), and that the clinical-action rule extends `REFUSAL_TRIGGERS`
> with a few `missing_data`-specific phrases (`"verify if still"`,
> `"response plan"`, `"recommend review"`, `"consider alternatives"`,
> `"cross-reactivity"`),
> to achieve a brief whose `missing_data` field is finally subject to
> the same "verified by construction" defense that already gates claims.

## Why a verifier rule, not just a prompt change

AgDR-0018 added prompt constraint #15 to bound `missing_data` prose. After
restarting uvicorn the model still emitted Hep A. The conclusion: the
prompt is a hint, not a contract. Pure prompt control is the right move
for low-cost guidance to the model but cannot be the trust story for a
clinical agent — the trust story has to be deterministic.

The pragmatic v1 design is "constrain by prompt; backstop by verifier."
The prompt now also calls out the deterministic rules by name (constraint
#15 and #16 in `brief_v1.txt`) so the model knows the verifier will drop
violating lines. This pairing is the same pattern used for claim text
(constraint #14 + `source_value_mismatch` rule).

## Decision detail

### `missing_data_clinical_action`

- Each `missing_data` entry is scanned against `REFUSAL_TRIGGERS` (the
  existing claim-text trigger list — "i recommend", "increase the dose",
  etc.) plus a small `missing_data`-specific list:
  - `"recommend review"`
  - `"verify if still active"`, `"verify if still"`
  - `"response plan"`
  - `"consider alternatives"`, `"if considering alternatives"`
  - `"cross-reactivity"`
- Matching entries are removed and a `missing_data_clinical_action`
  issue is appended to `verifier_issues` for observability.
- The `missing_data`-specific list was derived directly from the smoke
  walkthrough — every phrase on it is a real LLM emission against Maria
  G.'s chart.

### `missing_data_named_entity`

- Each `missing_data` entry is scanned for any keyword in
  `CLINICAL_ENTITY_KEYWORDS` (vaccines: hepatitis / hep a / hep b /
  influenza / tetanus / covid / mmr / varicella / shingles / zoster /
  pneumococcal / ppsv / etc.; drugs: metformin / lisinopril /
  atorvastatin / penicillin / etc.; labs: a1c / hba1c / ldl / hdl /
  egfr / etc.; conditions: diabetes / hypertension / etc.).
- For each keyword found in the entry, the rule then checks whether the
  same keyword appears in *any* cited packet's evidence text (the
  concatenation of `label`, `value`, `unit`, `observed_at`,
  `last_updated`, `status`, `field` across all packets). If not, the
  entry is dropped with a `missing_data_named_entity` issue.
- The keyword list is intentionally small (~50 entries) and static. It
  catches the high-frequency hallucination classes seen in the smoke
  walkthrough (Hep A, influenza, tetanus, COVID-19) without
  pretending to be a clinical vocabulary. A true vocabulary
  (RxNorm/SNOMED/CVX) is v2 work.
- Trade-off: a real chart with `Hepatitis B vaccine` in the packet
  would still allow `"no Hepatitis A vaccine on file"` to slip through
  if the LLM wrote `"hepatitis"` (matches B too). This is a known
  false-negative — preferable to false-positives that drop legitimate
  references.

### `claim.caveat` ISO date grounding

- `_check_source_value_grounding()` now also scans `claim.caveat` for
  ISO dates. Numbers in caveats are intentionally NOT checked because
  caveats commonly contain interpretive thresholds (`>90d ago`,
  `~3 months back`) that won't appear in packet evidence by design —
  enforcing free-number grounding there would false-positive on every
  legitimate staleness caveat.
- ISO dates are unambiguously specific, so a hallucinated date in a
  caveat (`"last updated 2024-01-01"` against a packet with
  `2025-10-15`) is a real grounding failure, not interpretive language.

### Empty-claims explicit message

- When `len(accepted) == 0` and `len(output.claims) > 0`, the verifier
  now appends `"No verified claims could be produced for this turn —
  all candidate claims failed verification. Open the chart panels
  directly."` to `missing_data`.
- Without this, a turn where every candidate claim was dropped renders
  as a near-empty card with only the dropped-count line — making it
  look like the brief just had nothing to say. The explicit message
  makes the failure mode visible to the physician.

## Tests

- `test_caveat_iso_date_must_be_in_evidence` — caveat with wrong ISO
  date is dropped with `source_value_mismatch`.
- `test_caveat_with_correct_iso_date_passes` — caveat citing the
  packet's actual date passes.
- `test_caveat_relative_thresholds_are_not_grounded` — caveats
  containing `>90d ago` and `~3 months` pass even though the numbers
  aren't in the packet (the carve-out is intentional).
- `test_missing_data_drops_clinical_action_phrasing` — three entries,
  two clinical-action, one benign — only the benign survives; two
  `missing_data_clinical_action` issues recorded.
- `test_missing_data_drops_invented_vaccine_name` — Pneumococcal
  packet only; entry mentioning Hep A / influenza / tetanus / COVID-19
  is dropped; benign category line survives.
- `test_missing_data_keeps_entity_mentioned_in_packet` — `pneumococcal`
  IS in the packet, so a missing_data entry mentioning it is kept.
- `test_all_claims_dropped_surfaces_explicit_message` — both candidate
  claims cite unknown source_ids, both dropped → explicit "no verified
  claims" line is present.

Pytest count: 55 → 62 (+7 new tests).
Eval count: 22/22 unchanged (no eval cases needed — the new rules
exercise the verifier directly, not the LLM).

## Files changed

- `agent/copilot-api/app/verifier.py` — `CLINICAL_ENTITY_KEYWORDS`
  list, `_sanitize_missing_data()` helper, caveat ISO date grounding,
  empty-claims explicit message; status logic now flips to
  `passed_with_drops` when sanitizer drops fire.
- `agent/copilot-api/app/prompts/brief_v1.txt` — strengthened
  constraint #15 (named-entity hallucination — calls out the
  Pneumococcal/Hep A worked example) + new constraint #16
  (no clinical-action language in `missing_data`).
- `agent/copilot-api/tests/test_verifier.py` — 7 new tests.

## Consequences

- The brief's `missing_data` field is now subject to deterministic
  verification, closing the last "verified by construction" gap. The
  thesis line ("read-only, current-patient, source-cited,
  value-grounded, verifier-gated") remains accurate end-to-end —
  before this AgDR, "verifier-gated" only described `claims`, not the
  full response.
- Future v2: the named-entity rule could be replaced with a real
  vocabulary lookup (CVX for vaccines, RxNorm for drugs, LOINC for
  labs) which would catch novel emissions the static list misses.
  Until then, the static list catches the demonstrated failure cases
  and degrades gracefully (false-negatives, not false-positives) on
  novel ones.
- The empty-claims explicit message changes the rendered UI for the
  worst-case turn — previously a blank-looking card, now an explicit
  "all claims failed verification, look at the chart" message. This
  is exactly the failure-visibility the audit-trail story requires.
