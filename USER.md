# USER.md — Target User, Workflow, and Use Cases

---

## Target User

**Dr. Sarah Clark, Primary Care Physician** — outpatient internal medicine, mid-sized clinic on OpenEMR.

| Attribute | Value |
|---|---|
| Schedule | 18–22 patients/day, 15-minute slots |
| Patient mix | Established panel, mostly chronic-disease management (diabetes, HTN, CKD), some acute |
| EHR experience | 4+ years on OpenEMR; competent power user, not an EHR enthusiast |
| Devices | Workstation in each exam room + a shared physician room with a docking station |
| Pain point | The 1–2 minutes she has between rooms is the only window to prepare for the next patient. It's never enough. She averages a chart scan of <90 seconds before walking in, and what she catches in that window determines the quality of the visit. |

### Why a Primary-Care Physician (and not an ED, hospitalist, specialist, or nurse)

I considered all of them. PCP wins for three reasons:

1. **Continuity multiplies the agent's value.** A PCP sees the same patient repeatedly. The most useful question, *"what changed since last visit?" only makes sense if there *is* a last visit. ED has no continuity. Specialists have it for a single dimension; PCPs have it across the whole patient.
2. **Volume.** PCPs see the most patients per day. Per-encounter efficiency gains compound across the schedule.
3. **Eval feasibility.** Eric raised this in the peer defense and it's a real point: a PCP who has seen the same patient 8 times can judge whether the agent's summary is accurate. An ED physician seeing a stranger has no ground truth. That makes PCPs the right user to *develop* the agent against, feedback loops actually close.

| Other user | Why not MVP target |
|---|---|
| Emergency physician | Fast intake, often-new patients, broader and higher-risk scope |
| Hospitalist | Inpatient rounding, different data cadence and handoff workflow |
| Specialist | More focused chart review; less need for cross-domain synthesis |
| Nurse | Different permissions and tasks; useful later for rooming and med reconciliation |
| Pharmacist | Medication-depth workflow deserves a dedicated interaction model |
| Resident | Supervised access pattern requires a different authorization model |

The architecture should support these roles later, but the MVP should not pretend one interface solves all clinical work. Week one is for one narrow user and a defensible agent.

---

## The Workflow: Moment by Moment

### Before the agent (today)

**8:54 AM** — Previous patient leaves. Dr. Clark has 1–2 minutes.
**8:55 AM** — Opens the next chart. Schedule says "diabetes follow-up." Chart has years of problems, meds, labs, messages, prior notes.
**8:56 AM** — Scans problem list, recent labs, meds, allergies, vitals, last note. Under time pressure, may miss a recent abnormal result, a medication change, or an old immunization due for follow-up.
**8:58 AM** — Walks into the room with an incomplete mental model. Has to recover context during the conversation.

### With the agent

**8:55 AM** — Dr. Clark opens the patient chart. **The Co-Pilot panel activates automatically.** Within 3 seconds, a card slides into the right rail with a pre-room briefing:

> **Maria G.  Diabetes follow-up**
>
> - **A1c is up:** 8.1% on 2026-04-20 (was 7.4% on 2026-01-15). [chart link]
> - **BP improved:** today's reading 128/78 (was 142/88 in March). [chart link]
> - **Active meds:** Metformin 500mg BID, Lisinopril 10mg daily, ASA 81mg. [chart links]
> - **Allergies:** Penicillin (rash). [chart link]
> - **Immunization history:** Pneumococcal recorded 2019; older entries flagged stale. (USPSTF/ACIP guideline-driven preventive logic is a v2 item — v1 surfaces records, not recommendations.)
> - **Not checked this turn:** specialty notes, imaging.
>
> *Sources: 6 records in this patient's chart. Click any claim to verify.*
>
> **Suggested actions:** [What changed?] [Medication check] [Allergy check] [Recent abnormal labs] [Immunizations] [Ask a question…]

**8:56 AM**  Dr. Clark reads. She catches the A1c spike and clicks the *Medication check* suggested action.

**8:57 AM**  Agent responds with the active medication list, reconciled across `prescriptions` and `lists`, and with any allergy conflicts cited. She asks via free-text: *"Did she fill her Metformin refill?"*

> *Metformin appears on the active prescription list (Metformin 500 mg BID). No fill or dispense record is present in the packets returned for this turn — pharmacy/dispense data is not yet wired in v1. To confirm adherence, check the pharmacy system directly.*

**9:00 AM**  Dr. Clark walks in knowing the actual clinical question — A1c is up despite Metformin being on the active prescription list. The visit starts with "how have things been going with the diabetes since March?" instead of "give me a minute to scan your chart."

**9:15 AM**  Visit ends. Dr. Clark documents, adjusts the Metformin dose, orders a repeat A1c in 3 months. **She doesn't use the agent during the encounter.** It's a between-rooms tool, not an in-room tool  by design.

---

## Agent Interaction Model: Not a Blank Chatbot

The first screen the physician sees is **not** a blank chat input. A blank chatbot under 90-second pressure forces the physician to invent a prompt at exactly the moment they have no time to invent anything.

The MVP interaction model is hybrid:

- **Automatic pre-room brief** rendered on chart open (no user action required).
- **Suggested action buttons** for the four most common follow-ups: *What changed? · Recent abnormal results · Medication check · Immunization history*.
- **Optional free-text follow-up** for questions the buttons don't cover.
- **Multi-turn context limited to the currently open patient** and the current chart session.
- **Source chips** on every claim; clicking opens the underlying record.
- **Failure states** rendered explicitly: missing data, stale data, conflicting data, tool unavailable.

This satisfies the case-study requirement for a conversational agent (free text remains available) while keeping the speed advantage of templated actions. The agent is conversational where conversation is useful — follow-ups, clarification, context-sensitive questions — not conversational for its own sake.

---

## Use Cases

Every agent capability shipped in v1 must trace back to one of these. Each maps to a tool or tool-set described in [Architecture.md](./Architecture.md).

**Implemented v1 use-case surface (7):**

| # | Use case | Gateway/LLM tool-planning shape |
|---|---|---|
| 1 | Pre-room briefing | Planner can select all six read-only tools; verifier gates every claim. |
| 2 | What changed since last visit? | Planner selects recent labs, problems, meds, allergies, and immunizations as needed. |
| 3 | Medication check | Planner selects identity, active medications, and allergies. |
| 4 | Allergy check | Planner selects identity, allergies, and active medications to surface conflicts. |
| 5 | Recent abnormal labs | Planner selects identity, active problems, and recent labs. |
| 6 | Immunization history | Planner selects identity and immunization history; no guideline recommendations in v1. |
| 7 | Free-text chart follow-up | Gateway refuses clinical-action/other-patient requests before tool planning; otherwise the LLM planner chooses the needed tools. |

### Use Case 1: Pre-Room Briefing

**Trigger:** Physician opens a patient chart.
**User question:** *"What do I need to know before I walk in?"*
**Agent behavior:** Within 3 seconds, surfaces a 4–6 bullet card with: chief complaint for today's visit, key changes since last visit, active meds + allergies, abnormal recent labs, and immunization history.
**Why an agent and not a dashboard:** Relevance filtering keyed on the reason for today's visit. A dashboard shows everything; the physician already has that and it's the problem, not the solution. Filtering "what matters today, given this is a diabetes follow-up" is a natural-language inference task.
**Architecture mapping:** Tier-1 packet builders fired in parallel + verifier + briefing template. Detail in [Architecture.md](./Architecture.md).

**Success criteria:**

- Initial response visible within 3 seconds of chart open.
- Every factual claim has a `source_id` and clickable citation.
- Physician can identify the visit's main issue without opening 3+ chart tabs.
- The agent clearly distinguishes "found nothing" from "did not check" (the `missing_data` field in the response).

---

### Use Case 2: "What Changed Since Last Visit?"

**Trigger:** Physician asks the question explicitly, or it's part of the briefing for any established patient.
**User question examples:** *"What changed since her March visit?" · "Anything new since I last saw him?" · "Were there any abnormal labs after the last appointment?"*
**Agent behavior:** Fetches recent labs, active medications, problems, allergies, and immunization records and surfaces what shifted since the prior captured packets. v1 does not consume external pharmacy fill/dispense feeds — adherence claims are framed against the prescription list, not days-of-supply.
**Example response:** *"Since the 2026-03-15 visit: A1c on 2026-04-20 shows 8.1% (up from 7.4% on 2026-01-15). BP today 128/78 (improved from 142/88). No new meds or diagnoses added. Pneumococcal record from 2019 is flagged stale; review immunization history."*
**Why an agent:** Cross-time, cross-table comparison is the synthesis task that no chart view does well. The physician currently does it by clicking through 4–5 tabs.
**Architecture mapping:** `RecentLabsPacketBuilder` + `ActiveMedicationsPacketBuilder` + `ActiveProblemsPacketBuilder` + `ImmunizationsPacketBuilder` + verifier value-grounding rule.

**Success criteria:**
- Comparison uses the correct previous visit date (verifier check).
- Every trend claim includes both old and new `source_id`s , single-source "trend" claims are rejected.
- Missing prior data is stated explicitly, not silently inferred.
- No old/inactive medication is presented as a new active medication.

---

### Use Case 3: Medication List Reconciliation (with Allergy-Conflict Surfacing)

**Trigger:** Physician asks about active meds, or the briefing surfaces a duplicate between `prescriptions` and `lists` proactively.
**User question examples:** *"Any medication changes since the last visit?" · "Is there anything in the med list that conflicts with her allergies?" · "What dose of Lisinopril is she on?"*
**Agent behavior:** Retrieves active meds (reconciled across `prescriptions` and `lists`) and allergies/reactions. Surfaces lists-vs-prescription duplicates as `claim_type=conflict`. Surfaces allergy/medication overlaps when the active medication name matches an allergen on file.
**Example response:** *"Metformin 500 mg BID is on the active prescription list. Lisinopril 10 mg PO daily appears in BOTH `prescriptions` AND `lists` — reconcile before prescribing. No active medication overlaps the documented Penicillin allergy."*
**Why an agent:** Natural-language input ("Metformin"), data-quality disambiguation across free-text drug names, and reconciliation across two source tables. A search box surfaces the prescription but doesn't answer the question.
**Architecture mapping:** `ActiveMedicationsPacketBuilder` (which reads both `prescriptions` and `lists`) + `AllergiesPacketBuilder` + verifier `lists_rx_conflict_unsurfaced` rule.

**Success criteria:**
- Active and stopped medications are not mixed without explicit labels.
- Duplicates across `lists` and `prescriptions` are identified, not double-counted.
- Allergy conflicts are surfaced as safety flags.
- The agent never declares a medication safe solely because no conflict was found in a partial dataset.

**Limitations called out in architecture:**
- Pharmacy fill / dispense / days-of-supply data is **not** consumed by v1. The agent says so explicitly when asked "did she fill her [med]?" rather than guessing.
- True drug-drug interaction checking requires an external service (RxNorm/DDI API) and is deferred to v2.

---

### Use Case 4: Allergy Check

**Trigger:** Physician clicks the *Allergy check* button, or the briefing flags a potential allergy/medication overlap.
**User question examples:** *"Any allergy conflicts with her current meds?" · "What is she allergic to?" · "Is Penicillin on her allergy list?"*
**Agent behavior:** Retrieves the allergy list and active medications, then surfaces any overlap between documented allergens and active medication names. Presents the allergy list with reactions noted; surfaces conflicts as `claim_type=conflict` claims.
**Example response:** *"Documented allergy: Penicillin (rash). No currently active medication matches the documented allergen. Active meds: Metformin 500 mg BID, Lisinopril 10 mg PO daily, ASA 81 mg."*
**Why an agent:** Allergy/medication reconciliation across two source tables (`lists_allergy` and `prescriptions`/`lists`) is a multi-step lookup that a search box doesn't answer. The physician asks one natural-language question and the agent resolves the join.
**Architecture mapping:** Planner selects `get_allergy_list` + `get_active_medications`; gateway executes both builders; verifier applies `lists_rx_conflict_unsurfaced` rule.

**Success criteria:**
- Every allergen is cited with source and documented reaction.
- Medication-allergen overlaps are surfaced explicitly, not silently ignored.
- Absence of an overlap is stated explicitly with caveats about data completeness, not declared safe by default.
- Drug-drug interaction checking is **not** in v1 scope; the agent does not attempt it.

---

### Use Case 5: Recent Abnormal Labs

**Trigger:** Physician asks proactively, or it's surfaced as a briefing bullet when abnormal flags exist.
**User question examples:** *"Any abnormal labs recently?" · "How did her A1c trend?" · "Any recent vitals out of range?"*
**Agent behavior:** Retrieves recent labs and vitals within a bounded window, prioritizes abnormal or visit-relevant values, cites date + value + unit + status for each result.
**Example response:** *"Recent labs (last 6 months): A1c 8.1% on 2026-04-20 (abnormal high; range 4.0–5.6). Creatinine 1.1 mg/dL on 2026-02-15 (in range). Lipid panel: LDL 142 on 2026-01-10 (high). No recent CBC."*
**Why an agent:** The raw lab table is high-density and often requires several clicks. The agent filters by recency, abnormal flag, and relevance to visit reason, and answers follow-up questions without forcing screen changes.
**Architecture mapping:** `get_recent_labs(months=6)` + verifier rule for status/range/unit completeness.

**Success criteria:**
- Every lab value includes date, units, abnormal flag (when present), and source.
- Preliminary or corrected results are explicitly labeled.
- A missing recent result is not treated as normal — verifier blocks "labs are normal" if any panel was not retrieved.
- Response stays short unless the physician asks to go deeper.

---

### Use Case 6: Immunization History

**Trigger:** Part of the pre-room briefing for any established patient.
**User question examples:** *"When was her last tetanus shot?" · "Does she have a pneumococcal on file?"*
**Agent behavior:** Surfaces immunization records the chart already contains, with date and stale-data caveats when records are older than the freshness threshold. v1 does **not** evaluate USPSTF or ACIP guidelines and does **not** declare anything "overdue" or "due now" — it shows what's on file and flags age/staleness for the physician to interpret.
**Example response:** *"Pneumococcal polysaccharide PPSV23 recorded 2019-10-12 — flagged stale (>5y). No tetanus or influenza records returned in the immunization packets for this turn."*
**Why an agent:** The raw immunization table is hard to scan and dates are often inconsistent across sources. The agent normalizes presentation and flags staleness, leaving guideline judgment to the physician.
**Architecture mapping:** `ImmunizationsPacketBuilder` + verifier `stale_data_uncaveat` rule.

**Success criteria:**
- Only source-supported records are shown.
- The agent distinguishes "no record found" from "guideline says not due."
- The agent does not invent guideline compliance or declare items "overdue" — that requires a guideline engine which is **v2 work**.
- The physician can dismiss an irrelevant entry via the feedback buttons.

**Limitation called out in architecture:** A USPSTF/ACIP-driven preventive-care recommendation engine (mammogram, colonoscopy, vaccine schedule) requires a vetted guideline rules table and is **not shipped in v1**.

---

### Use Case 7: Free-Text Chart Follow-Up

**Trigger:** Physician types a question into the free-text input after the auto-brief or a quick-action response.
**User question examples:** *"What dose of Lisinopril is she on?" · "When was her last tetanus shot?" · "Did she fill her Metformin refill?"*
**Agent behavior:** The gateway first checks the question against a local refusal ruleset: clinical-action requests ("increase her dose", "prescribe") and cross-patient requests ("what meds is John Smith on?") are refused before any LLM call is made. For allowed questions, the LLM planner (`POST /v1/tool-plan`) selects which of the six read-only tools are needed; the gateway executes them; the LLM synthesizes a verified answer.
**Why an agent:** Free-text reduces cognitive load for questions the buttons don't cover. The physician stays present with the patient rather than navigating tabs. The conversational interface also lets the physician ask follow-ups to a prior answer in the same session.
**Architecture mapping:** Gateway refusal ruleset → LLM tool planner → gateway-executed packet builders → verifier → structured claims → rendered answer.

**Success criteria:**
- Single-fact answers cite an exact `source_id`.
- Clinical-action requests are refused at the gateway; no sidecar call made.
- Cross-patient requests are refused at the gateway; no sidecar call made.
- Questions about data not present in v1 (pharmacy fill, dispense records) produce an explicit "not available in v1" statement, not a hallucinated answer.
- Ambiguous answers surface the ambiguity rather than picking one answer.

---

## What the Agent Explicitly Does NOT Do (v1)

Scoping is itself part of the design. These are deliberate non-goals:

- **No clinical recommendations.** Surfaces data; flags issues. Does not say "give her more Metformin."
- **No write operations.** Read-only. No prescribing, ordering, note-writing, or chart edits.
- **No cross-patient queries.** Scoped to the currently-open chart.
- **No free-text note RAG in v1.** Audit flagged as highest hallucination-risk path.
- **No new-patient intake workflow.** No longitudinal context to leverage.
- **No drug-drug interaction checking.** Requires external service. v2.
- **No proactive warnings about sensitive encounters being filtered.** OpenEMR's existing access controls handle filtering; v1 doesn't announce when filtering occurred. Acknowledged v2.

### What the Agent Must Refuse Outright

The agent should refuse or redirect, even when asked directly:

| Request | Response |
|---|---|
| "Diagnose this patient." | Refuse: out of scope. |
| "What medication should I prescribe?" | Refuse: out of scope. |
| "Open another patient's chart." | Refuse: agent is scoped to currently-open patient. |
| "Ignore the source requirement." / "Skip verification." | Refuse: source citation is mandatory. |
| "Use your general medical knowledge instead of the chart." | Refuse: only chart-grounded facts are returned. |
| "Write a note and sign it." | Refuse: read-only in v1. |
| "Show me hidden mental health or substance-use notes." | Refuse: respects OpenEMR sensitivity flags. |
| "Summarize everything in the database." | Refuse: minimum-necessary scope; current patient only. |

**Preferred refusal style** (concrete sentence the agent renders):

> *"I can surface verified chart facts for the currently-open patient, but I cannot diagnose, prescribe, or access records outside this chart. Try one of the suggested actions or ask about something specific to this patient."*

Refusals are logged the same way successful requests are — they are first-class events, not exceptions.

---

## Permissions and Role Assumptions

For MVP, the user is a physician with normal access to the currently-open patient's chart. The agent **inherits and narrows** that access.

Hard rules:

- The agent cannot answer about a patient who is not currently open in the chart.
- The agent cannot search for another patient by name, MRN, or any identifier.
- The agent cannot reveal sensitive encounters that OpenEMR would not show the physician via the UI.
- The agent cannot write to the chart.
- **Denied requests are audited as seriously as successful requests.**

Future role-specific versions may support nurses, residents, pharmacists, or hospitalists — but each gets different permissions, workflows, and eval datasets.

---

## Feedback Loop: How the Agent Improves

Dr. Clark can mark each response with one of five inline buttons:

| Button | Meaning | Eval consequence |
|---|---|---|
| **Helpful** | Answer was useful | Positive label; reinforces current behavior in eval set |
| **Missing important data** | Omitted something clinically important | Triggers an eval case to add data points to the briefing |
| **Incorrect** | Stated something wrong | Triggers an eval case; investigated for verifier gap |
| **Too slow** | Latency was unacceptable | Latency p95 alert; triggers caching/tier review |
| **Source unclear** | Citation didn't make sense | Triggers a citation/source-chip improvement |

Click writes two `trace_id`-keyed feedback events: (a) a Langfuse score on the trace for that turn (`name="clinician_feedback"`), and (b) an OpenEMR `agent_turn` audit row with the verdict in `comments`. v1 does **not** ship a dedicated `clinical_copilot_feedback` SQL table — Langfuse + the audit row already give us the trace_id-pivoted view the eval-suite expansion needs. A dedicated table is a v2 cleanup if/when the score view in Langfuse becomes the bottleneck.

A continuity-care PCP is the right MVP user for this loop *because* she has the ground truth to push these buttons accurately.

---

## Source of Truth for Architecture

Every architectural decision in [Architecture.md](./Architecture.md) flows directly from a constraint in this user document. Traceability:

| User constraint | Architecture decision |
|---|---|
| 90-second window | Tier-1 prefetch on chart open, Redis cache, target <3s |
| Continuity primary care | "What changed?" is a first-class tool |
| 90-second window + cognitive load | Pre-rendered briefing card + suggested-action buttons (not blank chatbot) |
| Clinical risk of hallucination | Read-only MVP, source packets, deterministic verifier |
| Dense chart navigation | Embedded UI inside OpenEMR, not separate app |
| Patient privacy | Current-patient binding, server-supplied `patient_uuid`, audit logs |
| Per-use-case "did she fill her Metformin?"-style questions | Free-text follow-up after templated actions |
| Real iteration vs. anecdote | Observability + feedback buttons + eval suite from day one |
| Multi-source meds (`lists` ∪ `prescriptions`) | Reconciliation in `get_active_medications` tool, conflict surfacing |
| Eval feasibility for the user | Feedback button taxonomy that maps to eval categories |

If an architecture decision can't be traced to a row in this table, it shouldn't be in the architecture.
