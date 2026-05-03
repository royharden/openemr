---
id: AgDR-0015
timestamp: 2026-05-02T19:10:00Z
agent: Claude Code
model: claude-opus-4-7
trigger: Slice A of plan_next02_opus47_2026-05-02_remediation_and_submission.md, in response to a codex audit finding that the lab portion of `seed_demo_patient.sql` wrote `procedure_result.procedure_order_id` (no such column) instead of going through `procedure_report`.
status: executed
---

# Demo lab seed routes through procedure_report

> In the context of OpenEMR's lab chain being three tables (`procedure_order
> → procedure_report → procedure_result`) and `RecentLabsPacketBuilder`
> requiring an INNER JOIN through all three,
> I decided to rewrite the seed to insert one `procedure_report` per order
> and reference `procedure_report_id` from each `procedure_result`,
> accepting that the rewrite makes the seed slightly longer (auto-increment
> chain via `LAST_INSERT_ID()` per order),
> to achieve a Maria G. demo patient whose lab packets actually surface in
> the brief — without the fix the demo had zero lab packets at runtime even
> though `pytest` and the evals (which use synthetic packets, not real SQL)
> were green.

## Decision detail

- Lab seed inserts in dependency order:
  1. `procedure_order` (per A1c/LDL test)
  2. `procedure_report` (one per order, `report_status='complete'`,
     `review_status='reviewed'`)
  3. `procedure_result` (referencing `procedure_report_id`,
     `result_status='final'`, with `units` and `range`)
- Demo values aligned with the user-facing demo script: A1c 7.2 (95d ago,
  normal), A1c 8.4 (5d ago, abnormal high), LDL 186 (8d ago, abnormal high).
- Idempotent: cascade-delete prior rows by `po.order_diagnosis IN
  ('demo-a1c','demo-ldl')` before re-insert.
- New `demo/validate_demo_patient.sql` runs the same join shape as
  `RecentLabsPacketBuilder` and asserts non-zero counts. If
  `lab_result_count != 3`, the seed didn't run cleanly.
- `demo/README.md` updated with the seed-then-validate run order and the
  expected count fingerprint, and a note about why the original
  bypass-`procedure_report` shape was wrong.

## Why this matters beyond "the demo works now"

This is the canonical OpenEMR lab join shape. Skipping `procedure_report` is
an easy mistake because some legacy code references `procedure_result.date`
directly without joining the report — but the report carries `date_collected`
and `date_report`, and the schema's foreign key is `procedure_report_id`,
not `procedure_order_id`. Future agents seeding labs (test fixtures, eval
seeds, smoke data) should follow this shape.

## Files changed

- `agent/copilot-api/demo/seed_demo_patient.sql` — labs section rewritten.
- `agent/copilot-api/demo/validate_demo_patient.sql` — new file.
- `agent/copilot-api/demo/README.md` — run-order updated; rationale added.

## Consequences

- The demo video can now actually show "Recent abnormal labs" producing
  real chips for Maria G., which is the core of the Week-1 demo.
- The validation script is a 5-second smoke that any future agent can run
  to confirm the seed survived a `dev-reset-install-demodata`.
- This finding underscores a broader lesson: passing pytest + passing evals
  is not the same as a working demo, because the test packets are synthetic.
  Real SQL fixtures need their own validation.
