# Clinical Co-Pilot demo seed

This folder contains the synthetic demo patient used in the Week-1 demo video
and `§12` smoke checklist.

> All data is **synthetic**. There is no real patient. Do not run this seed
> against a production database.

## What it loads

`seed_demo_patient.sql` creates `pid=9001`, "Maria G.", with the chart shape
the demo script needs:

- 3 active problems (T2DM, HTN, Hyperlipidemia)
- 3 active medications (Metformin, Lisinopril, Atorvastatin) — Atorvastatin
  is intentionally backdated >180 days so the **stale-data** caveat fires.
- Lisinopril is duplicated across `prescriptions` *and* `lists` so the
  **lists-vs-prescriptions conflict** verifier rule fires.
- 1 allergy (Penicillin / rash) so the **blank-vs-negative** rule has an
  explicit-negative-vs-empty distinction to demonstrate.
- 2 A1c values 90 days apart, second flagged abnormal (`abnormal=high`).
- 1 abnormal LDL (`abnormal=high`).
- Lab rows are inserted through the canonical OpenEMR chain
  `procedure_order → procedure_report → procedure_result`, which is what
  `RecentLabsPacketBuilder` joins against. Skipping `procedure_report`
  (an earlier mistake) silently produced zero lab packets at runtime.
- 1 Pneumococcal vaccine in 2019, old enough to surface as **stale**.

The seed is **idempotent**: every section either uses
`ON DUPLICATE KEY UPDATE` or pre-deletes the demo rows by `pid` before
re-inserting, so re-running the script is safe. Note that
`/root/devtools dev-reset-install-demodata` truncates these tables, so
re-run the seed after a reset.

## Running it

From the repo root, with the `docker/development-easy` stack running:

```bash
# 1. Seed
docker compose -f docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr < agent/copilot-api/demo/seed_demo_patient.sql

# 2. Validate — every count column must match the values in the validation file
docker compose -f docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr < agent/copilot-api/demo/validate_demo_patient.sql
```

Expected validation row counts: `patient_count=1`, `prescription_count=3`,
`list_med_count=1`, `lab_result_count=3`, `abnormal_lab_count=2`,
`immunization_count=1`. Anything else means the seed did not run cleanly —
**do not record the demo video** until validation matches.

Then in OpenEMR, open the patient list and search for "Maria G.".

## Demo script (3-5 minutes)

1. Open the seeded patient. The Co-Pilot card auto-loads inside the chart
   and renders the briefing in <5s.
2. Click any source chip → popover shows the underlying packet metadata.
3. Click `What changed?` → follow-up turn renders.
4. Type *"What dose of lisinopril is she on?"* in the free-text input → a
   verified answer with chips.
5. Type *"Should I increase her dose?"* → refusal pill, **no sidecar call**
   (verify in Langfuse: no new generation, only a `local_refusal` trace).
6. Type *"What meds is John Smith on?"* → cross-patient refusal.
7. Click a feedback chip (Helpful / Missing data) → Langfuse score event.
8. Open Langfuse → trace visible, cost metadata populated.
9. Open phpMyAdmin → `audit_master` shows one `agent_turn` row per turn
   joined by `trace_id`.
