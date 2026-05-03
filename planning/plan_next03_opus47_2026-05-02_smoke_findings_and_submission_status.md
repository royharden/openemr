# plan_next03_opus47 — Smoke Findings + Submission Path (STATUS)

**Status updated:** 2026-05-03T07:22:18Z by Codex / GPT-5.

### Update 2026-05-03T07:22:18Z - outstanding items rolled into Next04

The remaining review probes, Railway sidecar deployment, deployed smoke/denial matrix, demo/README finalization, and submission housekeeping have been moved into `planning/plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`. Next04 is now the active forward plan for both these leftovers and the instructor-feedback recovery work: 7 first-class use cases, gateway-orchestrated LLM tool planning, and 34+ behavioral evals. These items remain **not done** until completed by the Next04 implementation.

## Implementation status summary

| Slice | Status | Notes |
|---|---|---|
| M3. Panel-name hint in dropped-claim message | **Done** | New `_SOURCE_TABLE_TO_PANEL` map + `_panels_for_dropped` helper in `app/verifier.py`. `verify()` tracks `dropped_indexes` and emits panel-named missing-data line. 3 new pytest cases extending verifier coverage; existing `test_drops_unsupported_keeps_supported` updated to assert the fallback wording when the cited source is unknown. |
| M4. Bound `missing_data` prose to packet-supported categories | **Done** | Added constraint #15 to `app/prompts/brief_v1.txt` requiring `missing_data` entries to reference categories actually present in the packet set; explicit prohibition against inventing entity names (e.g. "Hepatitis A" when no Hep A packet exists). No code change. Manual-smoke probe covered in Slice M5. |
| M4b. Move Co-Pilot card to TOP of chart layout | **Done** | `Bootstrap.php` now subscribes to `RenderEvent::EVENT_SECTION_LIST_RENDER_BEFORE` (was `_AFTER`). The card now renders immediately before the section card loop in `interface/patient_file/summary/demographics.php` line 1350, putting it above demographics/problems/meds/labs widgets. |
| M5. Local browser walkthrough (15 steps incl. probes 11-13) | **Moved to Next04** | Logged-in browser smoke against Maria G. is mostly complete, including rendered card, no Hep A, grounded labs, follow-ups/free text, refusals, source-chip popover, sidecar-down HTTP 502, direct sidecar denials, forged-pid session binding, and decoded `agent_turn` audit row after the auditor fix. Remaining review probes (internal-error browser probe, Langfuse trace/cost review, and PHPStan level 10 completion) are now tracked in Next04. |
| M6. Railway sidecar deploy | **Moved to Next04** | Dockerfile is ready, but service is not provisioned. Railway private sidecar deployment is now tracked in Next04. |
| M7. Deployed §12 smoke + denial matrix | **Moved to Next04** | Depends on Railway deployment. The deployed denial matrix is now tracked in Next04 and expanded for LLM tool-planning/tool-argument denial cases. |
| M8. Demo video + README finalization | **Moved to Next04** | Final demo/README work is now tracked in Next04, including 7 use cases, LLM tool planning, source verification, Langfuse cost/tool metadata, and 34+ evals. |
| M9. Submission housekeeping | **Moved to Next04** | Final commit/push/status housekeeping remains user-driven and is now part of the Next04 implementation/submission pass. |
| **M4-followup. Verifier-side missing_data sanitizers + caveat ISO-date grounding** | **Done** | After the M4 prompt-only fix failed to prevent Hep A hallucination on the live smoke (2026-05-02 22:50Z), added deterministic verifier rules: `missing_data_clinical_action` (drops entries containing REFUSAL_TRIGGERS or `missing_data`-specific phrases like "verify if still active"), `missing_data_named_entity` (drops entries containing CLINICAL_ENTITY_KEYWORDS not in any packet evidence), caveat ISO-date grounding extension, and empty-claims explicit message. Pytest 55 → 62 (+7). Prompt also strengthened with constraint #16 + worked counter-example in #15. Recorded in AgDR-0019. |
| **M4-followup-2. Caveat clinical-action sanitization + ISO-only date enforcement** | **Done** | After the AgDR-0019 missing_data sanitizers landed, the 2026-05-03 smoke caught the model migrating clinical-action language into `claim.caveat` ("verify if still current", "verify which is authoritative", "confirm current status") and paraphrasing ISO dates into month-name form ("Jan 2026", "Oct 2025"). Added `caveat_clinical_action` verifier rule (exempts `claim_type=conflict` per constraint #8); hoisted shared `PROSE_ACTION_PHRASES` tuple; strengthened constraint #14 to ban month-name date paraphrasing with a worked counter-example. Pytest 62 → 65 (+3). Recorded in AgDR-0020. |

| **M4-followup-3. CVX immunization lookup + terminal packet smoke + claim-text action phrase scan** | **Done** | Fresh terminal packet dump showed live source evidence contained `"Hepatitis A 1"` because `ImmunizationsPacketBuilder` joined `list_options('immunizations')` on `cvx_code`; stock OpenEMR option_id `33` is Hep A, while CVX code `33` resolves through `codes` to pneumococcal. Fixed builder to use `code_types`/`codes` first and `list_options` by `immunization_id` only as fallback. Added `tests/packet_builders_smoke.php` and `validate_demo_patient.sql` pneumococcal assertion. Direct HTTP `/v1/brief` after uvicorn restart produced no Hep A. Same probe exposed `"verify current status"` in claim text; `PROSE_ACTION_PHRASES` now applies to claim text via `refusal_scope`. Pytest 65 -> 66 (+1). Recorded in AgDR-0021 and AgDR-0022. |

## Verification commands (M3/M4/M4b)

```powershell
cd agent/copilot-api
python -m pytest tests -q          # expect 66/66
python -m evals.runner             # expect 22/22

docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/packet_builders_smoke.php
# expect: PASS, 15 packets, immunization=pneumococcal polysaccharide vaccine, 23 valent

docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/router_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/sidecar_client_smoke.php
docker exec development-easy-openemr-1 php /var/www/localhost/htdocs/openemr/interface/modules/custom_modules/oe-module-clinical-copilot/tests/agent_turn_auditor_smoke.php

# Direct local sidecar denial probes completed 2026-05-03T05:38Z:
# - missing gateway secret header -> HTTP 422
# - bad gateway secret -> HTTP 403 invalid_gateway_secret
# - valid secret + missing task token -> HTTP 403 task_token_missing
# - valid secret + expired task token -> HTTP 403 task_token_expired
# - valid secret + tampered task token -> HTTP 403 task_token_signature
# - valid secret + patient hash mismatch -> HTTP 403 task_token_patient_mismatch

# In browser session for the remaining UI smoke:
# - Open Maria G.'s chart and confirm Co-Pilot card renders BEFORE the
#   demographics / problems / meds / allergies / labs cards.
# - Confirm missing_data says Pneumococcal (or a category-only immunization gap), not Hep A.
```

## Decisions recorded

- `agentdocs/decisions/AgDR-0017-dropped-claim-panel-hint.md`
- `agentdocs/decisions/AgDR-0018-missing-data-prose-bounded-by-prompt.md`
- `agentdocs/decisions/AgDR-0019-missing-data-deterministic-sanitizers.md`
- `agentdocs/decisions/AgDR-0020-caveat-clinical-action-and-iso-date-paraphrase.md`
- `agentdocs/decisions/AgDR-0021-cvx-backed-immunization-packets.md`
- `agentdocs/decisions/AgDR-0022-claim-text-action-phrase-scan.md`

See `agentdocs/Agent_LOG.md` 2026-05-03T05:01:00Z entry for the latest file-level changeset.

---

# Original plan (preserved verbatim below)

# plan_next03_opus47 — Smoke Findings + Submission Path

**Date:** 2026-05-02
**Author:** Opus 4.7 (planning, Claude Code) — handing off to a fresh agent because the prior conversation got long.
**Repo:** `C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr`
**Inputs the next agent should read first:**
- `planning/plan_next02_opus47_2026-05-02_remediation_and_submission.md` (the plan whose slices A–G have just been executed and live-verified).
- `planning/plan_next02_opus47_2026-05-02_remediation_and_submission_status.md` (per-slice status with live-verification notes).
- `agentdocs/Agent_LOG.md` head entries dated 2026-05-02T17:55Z, T19:10Z, T20:30Z (the planning + execution + smoke entries).
- `agentdocs/agent_lessons.md` head entries on schema gotchas + idempotency.
- Live: `agent/copilot-api/app/{verifier,prompts/brief_v1.txt}`, `interface/modules/custom_modules/oe-module-clinical-copilot/src/SourcePackets/ActiveMedicationsPacketBuilder.php` (already includes the `date_added → start_date → date_modified` fallback applied during smoke).

This is a **handoff plan**, not a redo. Slices A-G of plan_next02 have landed and have been live-verified end-to-end. Slices H-L of plan_next02 (browser walkthrough, Railway deploy, deployed denial matrix, demo video, commit + dual-remote push) were previously absorbed into this plan as Slices N3-Q3; their remaining unresolved work has now moved forward into `plan_next04_codex_wise_2026-05-03_gateway_tool_planning_evals_and_submission.md`.

---

## 1. What's already done (do NOT redo)

From plan_next02 slices A–G, all merged and live-verified locally:

- **Slice A — demo seed schema fix.** Lab section now inserts `procedure_order → procedure_report → procedure_result`. New `validate_demo_patient.sql` confirms the join shape. **Three additional seed regressions caught during smoke and fixed:** added missing NOT-NULL columns (`txDate`, `usage_category_title`, `request_intent_title`); backticked the reserved word `procedure_result.range`; made allergy + list-medication sections idempotent with title-scoped DELETEs. Final validate fingerprint: `1/3/1/3/1/3/2/1`. Idempotent across 3 sequential re-runs. Full ground truth in `agent/copilot-api/demo/{seed_demo_patient,validate_demo_patient}.sql`.
- **Slice B — verifier source-value grounding.** New `source_value_mismatch` rule in `app/verifier.py` (numbers + ISO dates only — prose-overlap deferred to v2). Prompt constraint #14 added. 9 new pytest cases; 4 new eval cases (19–22). Live brief on real LLM call confirmed the rule does not false-positive on legitimate matches: claims like `Hemoglobin A1c 8.4% (high, 2026-04-28)` and `LDL 186 mg/dL (high, 2026-04-25)` survive because every number + date appears verbatim in the cited packet.
- **Slices C + D — sidecar HTTP error semantics + brief.php exception redaction.** New `SidecarClient::classifyResponse()` static seam. `brief.php` now branches three ways (verified / errored / no-sidecar). 502 + audit `sidecar_failed` for the errored path; no auto-fallback to packet-flattening. Internal exceptions log full detail server-side and return only `{error: 'internal_error', trace_id}` to the browser. New `tests/sidecar_client_smoke.php` (6/6 passing).
- **Slice E — `llm.py` default model + `record_brief` router_family.** Default pinned to `claude-haiku-4-5-20251001`. `record_brief` accepts optional `router_family`. Source-pin guard test added.
- **Slice F — root `USER.md` synchronization.** "Preventive gaps" → "Immunization history" everywhere; days-of-supply / fill-history examples replaced with v1-truth wording; USPSTF/ACIP claims removed; feedback-loop language updated; broken `Claude_Architecture_v2.md` link replaced with `Architecture.md`. `planning/Users.md` carries a canonicality note pointing at root.
- **Slice G — test + lint sweep.** 53/53 pytest. 22/22 evals. 13/13 router smoke. 6/6 sidecar-client smoke. `php -l` clean on every changed PHP file.
- **Adjacent fix during smoke (not in plan_next02):** `ActiveMedicationsPacketBuilder.php` was reading `date_added` only, so the seeded Atorvastatin (200d ago, `date_added=NULL`) computed `freshness='unknown'` instead of `'stale'`, and the verifier's stale-data rule never fired. Fixed: `date_added → start_date → date_modified` fallback in both the SELECT ORDER BY and the freshness computation. Belt-and-suspenders: seed now also sets `date_added`. The next brief refresh confirmed Atorvastatin claims now drop without a staleness caveat (3 claims dropped vs 2 before).

**Pytest count after smoke:** 53/53. **Eval count:** 22/22.

---

## 2. New findings from the local browser smoke (2026-05-02 ~ 20:45Z)

The user opened Maria G.'s chart twice; the second refresh (after the Atorvastatin freshness fix) showed:

```
Maria G., 58-year-old female. [identity:patient_data:9001 ...]
Hemoglobin A1c increased from 7.2% (2026-01-28) to 8.4% (2026-04-28)... [lab:procedure_result:13, :14]
Recent abnormal labs: A1c 8.4% (high, 2026-04-28) and LDL 186 mg/dL (high, 2026-04-25). [lab:procedure_result:14, :15]

Missing: Medication dosing details for Metformin and Atorvastatin;
         Immunization status beyond 2019 Hepatitis A 1 dose;
         Possible duplicate medication conflict: lisinopril;
         3 claim(s) failed verification and were dropped — open the relevant chart panel.
```

Two issues, both real, both small:

### Finding 1 — Generic "open the relevant chart panel" message

The user pointed out the dropped-claim message could be more helpful. The verifier already has the `verifier_issues` list (with `claim_index`) and the `cited_packets` for each dropped claim — it knows which `source_table` each dropped claim cited. We can surface a panel-name hint by mapping `source_table` to friendly labels.

**Severity:** P3 UX polish. **Effort:** ~10 min. **Why ship:** the demo video shows this line; "open Medications and Labs panels" reads better than "open the relevant chart panel" and proves the verifier knows what it dropped.

### Finding 2 — `missing_data` prose hallucinated "Hepatitis A"

The chart's only immunization is Pneumococcal (CVX 33). The model's `missing_data` prose said *"Immunization status beyond 2019 Hepatitis A 1 dose"* — conflating the one immunization on file with Hep A. The verifier doesn't gate `missing_data` text today; it's free prose from the LLM.

**Severity:** P2. The brief is otherwise verifier-gated, so a hallucinated entity name in the missing line slightly weakens the "verified by construction" defense. **Effort:** 1-line prompt addendum. **Why ship:** in a demo, an attentive grader will spot "Hepatitis A" against a chart that has no Hep A and ask a question. Bound the model up front.

---

## 3. The plan — execute in order

### Slice M3 — Panel-name hint in dropped-claim message

**Files:**
- `agent/copilot-api/app/verifier.py` (add helper + replace the `dropped` line)
- `agent/copilot-api/tests/test_verifier.py` (extend the existing `test_drops_unsupported_keeps_supported` and add a new test)

**Tasks:**

1. Add a private helper near the bottom of `verifier.py`:

   ```python
   _SOURCE_TABLE_TO_PANEL = {
       "prescriptions":         "Medications",
       "lists":                 "Problems",          # default for type=lists
       "lists_medication":      "Medications",
       "lists_allergy":         "Allergies",
       "lists_problem":         "Problems",
       "procedure_result":      "Labs",
       "procedure_report":      "Labs",
       "procedure_order":       "Labs",
       "immunizations":         "Immunizations",
       "patient_data":          "Demographics",
       "form_encounter":        "Encounters",
   }

   def _panels_for_dropped(
       dropped_claim_indexes: list[int],
       claims: list[Claim],
       pkt_idx: dict[str, SourcePacket],
   ) -> list[str]:
       """Map dropped claims' cited packet source_tables to friendly panel names."""
       panels: set[str] = set()
       for i in dropped_claim_indexes:
           if i >= len(claims):
               continue
           for sid in claims[i].source_ids:
               pkt = pkt_idx.get(sid)
               if pkt is None:
                   continue
               panel = _SOURCE_TABLE_TO_PANEL.get(pkt.source_table, "")
               if panel:
                   panels.add(panel)
       return sorted(panels)
   ```

2. In `verify()`, track which claim indexes were dropped (the for-loop already increments `dropped` but doesn't keep the index; add a parallel `dropped_indexes: list[int]`).

3. Replace the existing message:

   ```python
   if dropped > 0:
       missing.append(
           f"{dropped} claim(s) failed verification and were dropped — open the relevant chart panel."
       )
   ```

   with:

   ```python
   if dropped > 0:
       panels = _panels_for_dropped(dropped_indexes, output.claims, pkt_idx)
       if panels:
           panel_phrase = " and ".join(panels) if len(panels) <= 2 else ", ".join(panels[:-1]) + f", and {panels[-1]}"
           missing.append(
               f"{dropped} claim(s) failed verification and were dropped — review the {panel_phrase} panel(s)."
           )
       else:
           missing.append(
               f"{dropped} claim(s) failed verification and were dropped — review the relevant chart panel."
           )
   ```

4. **Tests** to extend / add in `tests/test_verifier.py`:
   - Modify `test_drops_unsupported_keeps_supported` to assert the new message includes the word "Problems" (since the dropped claim cites `lists:does-not-exist` — actually the source is unknown, so this case will fall to the "no panel" fallback; choose a different fixture for this test, or assert the fallback wording).
   - Add `test_dropped_message_names_medications_panel`: cite a `prescriptions` packet with a wrong-dose claim → assert message contains "Medications".
   - Add `test_dropped_message_combines_multiple_panels`: drop one claim citing `prescriptions` and one citing `procedure_result` → assert message contains both "Medications" and "Labs".

5. Re-run `pytest tests -q` and `python -m evals.runner`. Fix any eval cases whose `missing_data_must_mention` expectations included the old phrasing (search `evals/cases/*.json` for `"open the relevant chart"` / `"failed verification"` and update if needed).

**Done when:** 56+/56+ pytest pass; 22/22 evals pass; rendering Maria G.'s chart shows e.g. *"3 claim(s) failed verification — review the Labs and Medications panel(s)"*.

### Slice M4 — Bound `missing_data` prose to packet-supported categories

**File:**
- `agent/copilot-api/app/prompts/brief_v1.txt`

**Tasks:**

1. Add a constraint #15 immediately after the existing #14 (source-value grounding):

   > 15. `missing_data` honesty. Every entry in `missing_data` must describe data we **could have had** for *this patient* — i.e. it must reference a category present in the supplied packets (medications, allergies, labs, immunizations, demographics, problems) **or** an explicit `field` from a packet you actually saw. Do not invent specific entity names (vaccine names, drug names, lab names, condition names) that do not appear anywhere in the packets. If you are noting an immunization gap, name only what's actually on the immunization packet list (e.g. "no influenza or tetanus vaccine on the immunization packet list"); do not invent vaccines like "Hepatitis A" that aren't in the packets.

2. No code change. The prompt is the contract.

3. **Optional** — add an eval case `23_missing_data_no_invented_entity.json` if it's quick: feed a single Pneumococcal CVX 33 packet, ask the briefing, assert that the verified response's `missing_data` does NOT contain the literal string `"Hepatitis A"`. Mark it `mode: "verifier"` (the eval runner exercises the verifier on canned `(LLMOutput, packets)` pairs — to test prose hallucination you'd need to run a real LLM call which the eval harness doesn't currently do). **If this needs an LLM, skip the eval case and rely on a manual smoke probe instead.** Do not block this slice on building an LLM-in-the-loop eval harness.

**Done when:** prompt updated; manual smoke (refresh Maria G. brief) shows the `missing_data` line no longer mentions Hepatitis A or any vaccine the chart doesn't have.

### Slice M4b — Move the Co-Pilot card to the TOP of the chart layout

**User request (2026-05-02):** the Co-Pilot card currently renders at the bottom of the chart UI. The user wants it at the **top** so it's the first thing visible when a chart opens — which matches the workflow described in `USER.md` ("opens the next chart… within 3 seconds, a card slides into the right rail").

**Files (likely):**
- `interface/modules/custom_modules/oe-module-clinical-copilot/Bootstrap.php` — find where the panel registers itself (event hook / Smarty template insert / dashboard widget priority).
- `interface/modules/custom_modules/oe-module-clinical-copilot/src/Controller/PanelController.php` — confirm the controller's render order.
- Possibly `interface/patient_file/summary/demographics.php` (or the Twig/Smarty template that drives the dashboard tile order) — the card may be appended via an event subscriber whose priority controls the order.

**Tasks:**

1. Read the existing `Bootstrap.php` to find which OpenEMR event the panel subscribes to. Likely candidates are `RenderEvent::EVENT_DASHBOARD_RENDER_SUMMARY` or a similar dashboard hook with a `priority` field, or it's appended via direct HTML injection into a fixed location.
2. If the panel uses an event-priority system, raise its priority so it renders first. OpenEMR dashboard event priorities follow Symfony's convention: **higher priority = earlier render**. Set priority to e.g. `1000` (well above the default `0` other widgets use).
3. If the panel injects HTML at a fixed location (e.g. appended to a specific `<div>`), re-target it to a parent earlier in the DOM. Check `interface/patient_file/summary/demographics.php` for the chart's main content rail and find the first `<div>` after the patient banner where injecting won't disrupt other widgets.
4. Test locally — refresh Maria G.'s chart and confirm the Co-Pilot card is the first thing visible below the patient banner.
5. **Watch for layout regressions.** Other chart widgets (problems, meds, labs lists) may rely on relative positioning. Confirm at least the patient banner + a couple of other widgets still render correctly after the change.

**Done when:** opening Maria G.'s chart shows the Co-Pilot card immediately below the patient banner, before the problem list / medications / labs widgets. No other widget breaks.

**Why this is small:** OpenEMR's dashboard system is event-driven and priority-aware. This is almost certainly a one-line priority change in `Bootstrap.php`. If it turns out to be more invasive (the panel renders via direct template injection into a hardcoded location), the next agent should propose moving to an event subscriber rather than fight the template.

### Slice M5 — Local browser walkthrough (was plan_next02 Slice H)

**Why now and not before M3+M4:** the user is running this manually. Doing it once after the two cosmetic improvements above means each follow-up button click validates the polished output, not the rough version they already saw.

The user has Docker running and Maria G. (`pid=9001`) loaded. The full §12 list from `plan_next01_opus47_..._status.md` applies. The new probes from plan_next02 still apply. Specifically the next agent should ask the user to:

1. Refresh Maria G.'s chart. Confirm the brief renders with grounded numbers + dates. Confirm the "X claim(s) failed verification" line names the right panels (Slice M3). Confirm the missing_data prose no longer mentions Hep A (Slice M4).
2. Click `What changed?` — confirm follow-up renders with grounded claims.
3. Click `Medication check` — confirm meds + allergies cited; Lisinopril conflict surfaced; Atorvastatin either dropped or carries a stale caveat.
4. Click `Allergy check` — confirm Penicillin cited; allergy/medication overlap reported if applicable.
5. Click `Recent abnormal labs` — confirm A1c 8.4% (high) and LDL 186 mg/dL (high) appear with `lab:procedure_result:*` chips.
6. Free-text **"What dose of lisinopril is she on?"** — expected: claim says `10 mg`, cited from `rx:prescriptions:*` or `med:lists:*`.
7. Free-text **"Should I increase her lisinopril dose?"** — expected: refusal pill, no sidecar call (verify in Langfuse no new generation, only a `local_refusal` trace).
8. Free-text **"What meds is John Smith on?"** — expected: cross-patient refusal.
9. Free-text **"Did she fill her Metformin refill?"** — expected: empty claims, missing_data line acknowledging no fill data in v1.
10. Click any source chip — confirm popover shows packet metadata (source_table, label, observed_at, freshness). Click the "Open record" link if the source_table is in the deep-link allowlist.
11. **Sidecar-error probe.** Stop the local sidecar (the prior agent had it running on port 8000 and stopped it; restart, then SIGTERM mid-flight). Refresh the brief. Confirm: HTTP 502 in DevTools network panel, brief shows refusal-styled "verification temporarily unavailable" message, audit row tagged `sidecar_failed`. Restart the sidecar before the next probe.
12. **Internal-error probe.** Briefly corrupt the gateway env (e.g. set `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=` to non-string by editing the `docker-compose` env, OR force a session error). Confirm response payload contains `error: internal_error` + `trace_id` only — NO `message` field with stack content. Restore the env.
13. **Forged pid probe.** In DevTools, mutate the `pid` POST field for the brief request. Confirm server uses session pid; audit row shows session pid; no leak.
14. Open phpMyAdmin. `SELECT * FROM audit_master WHERE event='agent_turn' ORDER BY date DESC LIMIT 10;` — confirm rows match Langfuse traces by `trace_id`.
15. Open Langfuse. Confirm traces from local turns are visible with cost metadata; `router_family` metadata present on free-text turns.

**If any of 1–10 fail**, the next agent fixes the bug and re-runs that step before moving on. **Probes 11–13 are the new ones** introduced by plan_next02 Slices C/D — they MUST pass before deploy.

**Done when:** every step above is verified, with notes appended to `agentdocs/Agent_LOG.md`. Screenshots stored in `agentdocs/smoke/` are nice-to-have, not required.

### Slice M6 — Railway sidecar deploy (was plan_next02 Slice I)

Use the existing Dockerfile in `agent/copilot-api/Dockerfile`.

**Railway service `copilot-api` env:**
- `ANTHROPIC_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST=https://us.cloud.langfuse.com`
- `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<random 32-byte hex>` — generate fresh; do NOT reuse the local `local-dev-shared-secret`.
- `COPILOT_MODEL=claude-haiku-4-5-20251001`
- `COPILOT_REQUIRE_TASK_TOKEN=1` (default in code is also 1; set explicitly for auditability).
- `COPILOT_ENV=production`
- `PORT=8000`

**OpenEMR service env additions** (whichever Railway service hosts OpenEMR for the demo, OR keep local Docker as the demo target):
- `COPILOT_API_BASE_URL=http://${{copilot-api.RAILWAY_PRIVATE_DOMAIN}}:8000`
- `COPILOT_OPENEMR_GATEWAY_SHARED_SECRET=<same as sidecar>`

**Hard requirements:**
- **No public domain on `copilot-api`.** Private networking only. The whole defense story turns on the sidecar not being internet-addressable.
- Healthcheck `GET /healthz` returns 200.
- Deploy logs show no `ANTHROPIC_API_KEY` redaction misses.

**Fallback (documented option):** if Railway DB seeding for the demo patient is hard, record the demo against local Docker and note in the README that the deployed instance uses a different demo patient. The PRD doesn't require a specific deployed demo patient.

**Done when:** Railway shows both services healthy; private networking confirmed; the user can hit healthz from inside the Railway shell but not from the public internet.

### Slice M7 — Deployed §12 smoke + denial matrix (was plan_next02 Slice J)

Repeat Slice M5 against the deployed URL. Add the explicit denial matrix:

| Attempted attack | Expected result |
|---|---|
| Forged `pid` in POST body | session pid wins; audit unchanged |
| Missing `csrf_token_form` | 403, `csrf_failure` audit |
| Logged-out `/brief.php` | 403/redirect, no audit |
| Sidecar called directly w/o `X-Copilot-Gateway-Secret` | 422 (FastAPI required-header) |
| **Sidecar w/ secret + missing token** | **403 `task_token_missing` (Slice 1 + plan_next02 Slice C)** |
| **Sidecar w/ secret + expired token** | **403** |
| **Sidecar w/ secret + tampered HMAC** | **403** |
| **Sidecar w/ secret + mismatched `patient_uuid_hash`** | **403** |
| **Gateway sees sidecar 4xx** | **HTTP 502 to browser, audit `sidecar_failed`, no leaked detail** |
| **Gateway internal exception** | **HTTP 500 with `error=internal_error` + `trace_id` only, no message** |

Each row gets a UTC-timestamped entry in `agentdocs/Agent_LOG.md`.

**Done when:** every row above is verified against the deployed URL, with timestamps logged.

### Slice M8 — Demo video + README finalization (was plan_next02 Slice K)

- **Record the local-only backup video FIRST** before depending on the deployed URL — this is the failure-mode mitigation from the original Opus plan. If Loom or Railway hiccup the night of submission, you still have a video.
- Demo script (3-5 min):
  1. Open deployed URL → log in as `admin` → search Maria G. → Co-Pilot card auto-renders.
  2. Read the brief on camera. Highlight `lab:procedure_result:*` chips and the panel-name dropped-claims hint (Slice M3 polish).
  3. Click a source chip → popover. Click "Open record" if mapping exists.
  4. Click `Recent abnormal labs` → verified A1c 8.4% + LDL 186 mg/dL.
  5. Free-text **"What dose of lisinopril is she on?"** → verified `10 mg` answer with chip.
  6. **The value-grounding probe.** Say on camera something like *"and if the model had written `100 mg` instead of `10 mg`, the verifier would have dropped that claim — that's the source-value-grounding rule."* This sells the core trust feature directly.
  7. Free-text **"Should I increase her dose?"** → refusal pill, no sidecar call.
  8. Open Langfuse → trace visible, cost metadata populated, `router_family` filterable.
  9. Show the audit row in phpMyAdmin.
  10. Show `python -m evals.runner` running 22/22.
  11. Read the cost analysis line on camera: per-turn cost; 10K-user projection.
- Update root `README.md`, module `README.md`, and `agent/copilot-api/README.md` with:
  - Deployed URL + login note.
  - Demo video URL.
  - `agent/copilot-api/evals/cases/` + `eval_results.json` link.
  - `planning/cost_analysis.md` link in a "Cost Analysis" section.
  - Link to `AUDIT.md` and root `USER.md`.
  - Sidecar local-run instructions (or link to `agent/copilot-api/README.md`).
  - One-line thesis: *"A clinical agent intentionally constrained — read-only, current-patient, source-cited, value-grounded, verifier-gated, observable, deployed."*

### Slice M9 — Submission housekeeping (was plan_next02 Slice L)

- Confirm root has `AUDIT.md`, `USER.md`, `ARCHITECTURE.md` (or stubs that link to `planning/`). All three exist as of 2026-05-02.
- Conventional Commits + `Assisted-by: Claude Code` trailer per repo memory.
- Push to both `origin` (GitHub) and `gauntlet` (GitLab).
- Mark `plan_next01_opus47_..._status.md` slices 8–12 done in the same pass.
- Mark `plan_next02_opus47_..._status.md` slices H–L done in the same pass.
- Mark this plan's `_status` copy slices M3–M9 done.
- New AgDR sequential numbers (latest = `AgDR-0016`):
  - `AgDR-0017-dropped-claim-panel-hint.md` (Slice M3 — small UX, but pinning the source_table → panel mapping is worth recording).
  - `AgDR-0018-missing-data-prose-bounded-by-prompt.md` (Slice M4 — explains why this is a prompt fix and not a verifier rule for v1).
- Append a final entry to `agentdocs/Agent_LOG.md` with a short `submission_complete` summary.

---

## 4. Submission readiness gate

Don't proceed to demo recording until **all** of these are true:

- [ ] Slice M3 panel-name hint visible in the rendered brief (e.g. *"…review the Labs and Medications panel(s)."*).
- [ ] Slice M4 prompt addendum landed; refreshed brief no longer hallucinates a Hep A line on the Pneumococcal-only chart.
- [ ] Slice M4b — Co-Pilot card renders at the top of the chart layout, immediately under the patient banner.
- [ ] All 15 steps of Slice M5 pass locally, including probes 11–13.
- [ ] Railway deploy healthy; private networking enforced.
- [ ] Slice M7 denial matrix all green against deployed URL.
- [ ] 53/53 pytest, 22/22 evals (or +1 if the optional eval 23 was added).
- [ ] PHP CLI smokes green inside container.
- [ ] PHPStan level 10 clean on every changed PHP file (**Moved to Next04** local verification gate, because Next04 introduces additional tool-planning PHP changes that need the same pass).
- [ ] Local-only backup demo video recorded.

Only after that should the next agent press record on the final demo video.

---

## 5. Things that are NOT this plan's job

The cuts list from `plan_next01_opus47` §7 still applies. In addition:

- **Building an LLM-in-the-loop eval harness** to test `missing_data` prose hallucination at scale. Slice M4's prompt addendum + a manual smoke probe is enough for v1. v2 would extend the eval runner with a `mode: "live_llm"` that calls the sidecar end-to-end against canned packets — out of scope for Week 1.
- **A condition-prose token-overlap verifier rule.** Codex's Finding 1 also proposed this; plan_next02 narrowed it to numbers + ISO dates only. Do not widen the rule in this plan.
- **A dedicated `clinical_copilot_feedback` SQL table.** Langfuse score + `agent_turn` audit row already cover the rubric. Documented in `USER.md`.
- **Refactoring `brief.php` into a Gateway class.** Pure tidiness, no rubric credit.

---

**Thesis line (carry into the demo video and README, unchanged from plan_next02):**
> *A clinical agent intentionally constrained — read-only, current-patient, source-cited, value-grounded, verifier-gated, observable, and deployed — because in a clinical context the trustworthy 30% beats the impressive 80%.*

---

## 6. One-line execution order

`M3 → M4 → M4b → M5 → M6 → M7 → M8 → M9.`

M3 + M4 + M4b can be a single PR (each is a few lines / one priority change). M5 is a manual walkthrough that can ride the same conversation. M6–M7 are environmental. M8 is the video. M9 closes the box.
