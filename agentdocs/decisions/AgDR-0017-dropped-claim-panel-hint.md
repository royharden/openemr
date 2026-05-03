---
id: AgDR-0017
timestamp: 2026-05-02T22:30:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Slice M3 of plan_next03_opus47_2026-05-02_smoke_findings_and_submission.md, in response to a local browser smoke finding (2026-05-02 ~20:45Z) where Maria G.'s rendered brief showed a generic "open the relevant chart panel" message after the verifier dropped 3 claims. The user noted the line could be more helpful since the verifier already knows which `source_table` each dropped claim cited.
status: executed
---

# Verifier names the chart panels behind dropped claims

> In the context of the verifier's missing-data line generically saying
> "open the relevant chart panel" whenever any number of claims were
> dropped, even though `verifier_issues` already carries `claim_index`
> and the cited packets are still in the in-memory packet index,
> I decided to map each dropped claim's cited packets through a
> `(source_table, resource_type) → panel name` table and emit the
> friendly panel name(s) in the missing-data line — e.g. "review the
> Labs and Medications panel(s)" instead of the generic phrase,
> accepting that the mapping must distinguish problems / allergies /
> medications inside the `lists` table by `resource_type`,
> to achieve a demo-line that proves the verifier knows what it
> dropped and tells the physician exactly where to look in the chart.

## Decision detail

- New module-level dicts in `app/verifier.py`:
  - `_SOURCE_TABLE_TO_PANEL` for direct mappings (`prescriptions →
    Medications`, `procedure_result → Labs`, `immunizations →
    Immunizations`, `patient_data → Demographics`, plus forward-compat
    entries for `procedure_report`, `procedure_order`, `form_encounter`).
  - `_LISTS_RESOURCE_TO_PANEL` for the three `lists` resource types this
    project actually emits (`Condition → Problems`, `AllergyIntolerance
    → Allergies`, `MedicationStatement → Medications`).
- New helpers `_panel_for_packet(packet)` and `_panels_for_dropped(
  dropped_indexes, claims, pkt_idx)`.
- `verify()` tracks a parallel `dropped_indexes: list[int]` alongside the
  existing `dropped` counter so the helper can re-walk the dropped
  claims' cited packets after the per-claim loop.
- The phrasing logic combines panels with `and` (two panels), an Oxford
  comma list (three+), or just the bare panel name (one).
- Fallback wording — "review the relevant chart panel" — fires when no
  cited packet is in `pkt_idx` (the dropped claim cited an unknown
  source_id, which is itself a `source_attribution` failure).

## Why a dict, not a regex on `source_id`

`source_id` strings (`rx:prescriptions:1`, `lab:procedure_result:14`)
contain the source_table by convention, but parsing them by regex would
silently fail for any future packet builder that uses a different
prefix. The `source_table` and `resource_type` fields on `SourcePacket`
are already the contract — keying off them stays correct as new
builders are added.

## Tests

- `tests/test_verifier.py::test_drops_unsupported_keeps_supported`
  (modified) now asserts the fallback wording fires when the dropped
  claim cites an unknown source_id, since `_panels_for_dropped` finds
  no packet in the index.
- New `test_dropped_message_names_medications_panel` — a `prescriptions`
  packet plus a wrong-dose claim (`100 mg` against a `10 mg` packet,
  caught by `source_value_mismatch`) → message contains "Medications".
- New `test_dropped_message_combines_multiple_panels` — drops one claim
  citing `prescriptions` and one citing `procedure_result` → message
  contains both "Medications" and "Labs".

## Files changed

- `agent/copilot-api/app/verifier.py` — `dropped_indexes` tracking,
  `_panels_for_dropped` + `_panel_for_packet` + the two mapping dicts,
  panel-aware phrasing in the missing-data line.
- `agent/copilot-api/tests/test_verifier.py` — modified 1 test, added
  2 tests.

## Consequences

- The demo brief shipped on the recorded video now reads "review the
  Labs and Medications panel(s)" rather than "open the relevant chart
  panel." Small win for the grader's first read of the rendered output;
  also a small but real signal that the verifier's drop reasons are
  load-bearing instead of decorative.
- Future packet builders that introduce a new `source_table` will
  silently fall through to the empty string and trigger the fallback
  wording. That's intentional: we'd rather degrade to the generic line
  than misname a panel. New builders should add a row to
  `_SOURCE_TABLE_TO_PANEL` (or `_LISTS_RESOURCE_TO_PANEL` for `lists`).
- This change is verifier-only; the prompt is unchanged. The LLM
  doesn't see panel names in the contract.
