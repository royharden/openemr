"""ADA 2026 Standards of Medical Care in Diabetes — locally-authored summaries.

Copyright posture
-----------------
The official ADA Standards of Medical Care in Diabetes is a copyrighted
publication.  This module commits **no copyrighted guideline body text**.
Each chunk below is an *original summary* of an ADA 2026 recommendation
written in the primary-care educator's own words.  The canonical source URL
is recorded in ``source_url`` metadata only; the chunk text never reproduces
guideline prose.  See Plan §6.4 (copyright guard requirement).

Authoring rule of thumb (Plan §6.4, also documented in agent_lessons):
  - Never paraphrase >30 consecutive words of guideline body text.
  - Describe each recommendation in plain language for PCPs.
  - The official URL goes in source_url metadata, not in chunk text.

Source metadata
---------------
source_id            : ADA-SoC-2026
source_organization  : ADA
source_name          : ADA 2026 Standards of Medical Care in Diabetes
source_year          : 2026
source_url           : https://professional.diabetes.org/standards-of-care
recommendation_grade : per chunk, ADA grading (A/B/C/E)
"""

from __future__ import annotations

import logging
from typing import Any

from ..chunker import ChunkSource, chunk_text
from ..contracts import GuidelineChunk

logger = logging.getLogger(__name__)

SOURCE_ID = "ADA-SoC-2026"
SOURCE_ORGANIZATION = "ADA"
SOURCE_NAME = "ADA 2026 Standards of Medical Care in Diabetes"
SOURCE_YEAR = 2026
SOURCE_URL = "https://professional.diabetes.org/standards-of-care"

# Plan §6.4 + AgDR-0070 — distinctive verbatim phrases from the official ADA
# publication. The `--check-corpus-copyright` scan trips on any chunk text
# containing these substrings (case-insensitive). Update this list when a new
# section is summarized and you spot a candidate signature phrase. Authoring
# rule: locally-authored summaries describe each recommendation in plain
# English for PCPs and never reproduce ADA prose verbatim.
COPYRIGHT_TRIP_PHRASES: list[str] = [
    # ADA's em-dash + year convention is distinctive to the official publication.
    "Standards of Medical Care in Diabetes—2024",
    "Standards of Medical Care in Diabetes—2025",
    "Standards of Medical Care in Diabetes—2026",
    # Distinctive ADA evidence-grade labels in their exact published form.
    "Evidence Level A:",
    "Evidence Level B:",
    # ADA's signature recommendation phrasings (these would only appear if
    # somebody copy-pasted from a Diabetes Care issue verbatim).
    "Diabetes Care 2026;",
    "[ADA position statement]",
]


# ---------------------------------------------------------------------------
# Locally-authored summaries (original phrasing only — NO copyrighted text).
# Each entry: (chunk_slug, short_label, ada_grade, summary_text)
# ---------------------------------------------------------------------------
_ADA_2026_SUMMARIES: list[tuple[str, str, str | None, str]] = [
    (
        "a1c-target-tiers",
        "A1c target tiers by patient population",
        "B",
        """# A1c Target Tiers (ADA 2026 — locally-authored summary)

## Summary
Glycemic targets are individualized in the ADA 2026 framework rather than a
single number for all patients. Most non-pregnant adults aim for an A1c below
7 percent if that target can be reached without burdensome hypoglycemia. A
tighter target near 6.5 percent is reasonable for younger patients with a
short diabetes duration who are not on insulin or sulfonylureas. A looser
target between 7.5 and 8 percent is appropriate for frail older adults,
limited life expectancy, advanced microvascular or macrovascular
complications, or a history of severe hypoglycemia.

## Pregnancy
Pregnancy targets are stricter: fasting glucose below roughly 95 mg/dL and
one-hour postprandial below roughly 140 mg/dL, individualized to avoid
hypoglycemia. A1c below 6 percent during pregnancy is preferred when it can
be achieved safely.

## Primary-care takeaway
Always pair the A1c number with hypoglycemia risk, comorbidities, life
expectancy, and patient preference. Document the chosen target in the chart
so the next visit can confirm it is still appropriate.
""",
    ),
    (
        "metformin-initiation",
        "Metformin starting dose and titration",
        "A",
        """# Metformin Initiation and Titration (ADA 2026 — locally-authored summary)

## Summary
Metformin remains the preferred first-line oral agent for most adults with
type 2 diabetes when there is no contraindication. A typical starting dose
is 500 mg once daily with the largest meal to minimize gastrointestinal
upset. The dose is then titrated upward every one to two weeks as tolerated
toward a usual maintenance dose of 1500 to 2000 mg per day in divided doses,
with a maximum near 2550 mg per day.

## Tolerability tips
- Extended-release formulations reduce GI side effects and can be tried if
  immediate-release is poorly tolerated.
- Take with food.
- Transient nausea, loose stools, and abdominal discomfort are common in the
  first week and usually resolve.

## When not to start
Do not initiate at full dose. Do not start in patients with acute illness
involving dehydration, severe hepatic impairment, or unstable heart failure.
Renal thresholds are covered in a separate summary chunk.
""",
    ),
    (
        "metformin-egfr-thresholds",
        "Metformin and eGFR thresholds",
        "A",
        """# Metformin and Renal Function (ADA 2026 — locally-authored summary)

## Summary
Renal safety for metformin is decided by eGFR, not by serum creatinine alone.

- eGFR at or above 45 mL/min/1.73 m²: standard dosing.
- eGFR 30 to 44 mL/min/1.73 m²: use with caution; do not start metformin in
  this range and consider reducing the dose in patients already on therapy.
  Monitor eGFR at least every three to six months.
- eGFR below 30 mL/min/1.73 m²: contraindicated; discontinue.

## Hold-during-illness rule
Metformin should be held during acute illness with risk of volume depletion
or contrast-induced nephropathy, and restarted only after renal function is
confirmed stable. The driver is lactic acidosis risk from accumulation when
renal clearance falls.
""",
    ),
    (
        "glp1-cv-indication",
        "GLP-1 receptor agonists with established cardiovascular disease",
        "A",
        """# GLP-1 Receptor Agonists for ASCVD (ADA 2026 — locally-authored summary)

## Summary
In adults with type 2 diabetes who also have established atherosclerotic
cardiovascular disease (prior MI, stroke, or symptomatic peripheral arterial
disease), a GLP-1 receptor agonist with proven cardiovascular benefit is
recommended independently of baseline A1c and independently of metformin
use. Agents in this class with cardiovascular outcome data include
semaglutide, liraglutide, and dulaglutide.

## Practical use
- Start at the lowest dose and titrate to limit nausea.
- Monitor for pancreatitis symptoms and discontinue if pancreatitis is
  suspected.
- Counsel on injection technique for the subcutaneous formulations and on
  swallowing instructions for the oral formulation if used.
- Modest weight loss is a frequent secondary benefit; reinforce with
  nutrition and activity counseling.

## Combinations
GLP-1 receptor agonists may be added on top of metformin, SGLT2 inhibitors,
or basal insulin. Concurrent use of DPP-4 inhibitors is not recommended
because both classes work through the incretin axis.
""",
    ),
    (
        "sglt2-hfref-ckd-indication",
        "SGLT2 inhibitors in HFrEF and CKD",
        "A",
        """# SGLT2 Inhibitors for Heart Failure and CKD (ADA 2026 — locally-authored summary)

## Summary
In adults with type 2 diabetes who have heart failure with reduced ejection
fraction, an SGLT2 inhibitor with cardiovascular benefit is recommended
regardless of baseline A1c. The same agents are recommended for type 2
diabetes with chronic kidney disease, particularly when albuminuria is
present, to slow CKD progression and reduce cardiovascular events. Agents
with supporting evidence include empagliflozin, dapagliflozin, and
canagliflozin.

## Initiation thresholds
- Generally avoid initiating an SGLT2 inhibitor at very low eGFR; agent-
  specific eGFR thresholds for initiation are typically in the 20 to 30
  mL/min/1.73 m² range. Continuation past initiation is often acceptable to
  even lower eGFR for renal protection.
- Hold during acute illness with volume depletion.

## Counseling
- Diabetic ketoacidosis can occur at near-normal glucose levels; warn about
  symptoms and instruct patients to hold the drug and seek care for nausea,
  vomiting, or rapid breathing.
- Increased risk of genital mycotic infections; counsel on perineal hygiene.
- Volume depletion and modest blood pressure reduction are expected;
  reassess loop diuretic dose at initiation.
""",
    ),
    (
        "insulin-initiation",
        "Insulin initiation thresholds in type 2 diabetes",
        "B",
        """# Insulin Initiation in Type 2 Diabetes (ADA 2026 — locally-authored summary)

## Summary
Consider starting basal insulin when oral and non-insulin injectable therapy
is no longer maintaining the patient's individualized A1c target, when the
A1c is markedly above goal (commonly more than about 1.5 to 2 percentage
points above target), or when symptoms of hyperglycemia and weight loss
suggest insulin deficiency. Severe hyperglycemia with ketosis or A1c above
10 percent is a stronger indication for early insulin.

## Practical starting plan
- Basal insulin (analogs such as glargine or degludec) at 0.1 to 0.2
  units/kg/day, or 10 units once daily, whichever is lower.
- Titrate by 2 units every 3 days based on fasting glucose, aiming for a
  fasting target of roughly 80 to 130 mg/dL individualized to the patient.
- Continue metformin and other agents with proven cardiorenal benefit
  whenever possible.

## When to add prandial insulin
If basal insulin is titrated to target fasting glucose but A1c remains
above goal, add a prandial insulin dose at the largest meal or consider
switching to a GLP-1 receptor agonist if not already in use.
""",
    ),
    (
        "hypoglycemia",
        "Hypoglycemia risk and management",
        "B",
        """# Hypoglycemia Risk and Management (ADA 2026 — locally-authored summary)

## Summary
Assess hypoglycemia risk at every diabetes-focused visit. Level 1
hypoglycemia is defined as a measured glucose below 70 mg/dL, level 2
below 54 mg/dL, and level 3 is any severe event requiring assistance from
another person regardless of glucose value.

## Higher-risk groups
- Patients on insulin or sulfonylureas.
- Older adults with cognitive impairment or impaired hypoglycemia awareness.
- CKD, hepatic impairment, prior severe hypoglycemia, and alcohol use.

## Management
- Conscious patient: 15 grams of fast-acting carbohydrate (glucose tablets
  preferred), recheck glucose in 15 minutes, repeat if still below 70 mg/dL,
  and follow with a meal or snack.
- Severe hypoglycemia: glucagon (nasal or subcutaneous/intramuscular),
  prescribed for any patient on insulin or sulfonylurea with risk factors.
  Train at least one family member or caregiver.
- After any level 2 or 3 event, review and adjust the regimen; consider
  loosening A1c target if events recur.
""",
    ),
    (
        "annual-screening",
        "Annual screening: foot, eye, kidney",
        "B",
        """# Annual Complication Screening (ADA 2026 — locally-authored summary)

## Summary
At least annually, adults with diabetes should have a structured screen for
the three high-yield complications:

- Foot: comprehensive foot exam including inspection, pulses, and
  monofilament testing for protective sensation. More frequent inspection
  if loss of protective sensation, prior ulcer, or amputation.
- Eye: dilated retinal exam by an ophthalmologist or optometrist, or a
  validated retinal photography program. In well-controlled type 2 diabetes
  with no prior retinopathy, screening can be extended to every 1 to 2
  years per the clinician's judgment.
- Kidney: annual urine albumin-to-creatinine ratio and eGFR. More frequent
  if albuminuria is present or eGFR is declining.

## Documentation tip
Track these as recurring health-maintenance items so the chart highlights
the next due date. A reminder on the problem list helps with patient
hand-offs.
""",
    ),
    (
        "lifestyle-cornerstones",
        "Lifestyle modification: nutrition and physical activity",
        "A",
        """# Lifestyle Modification Cornerstones (ADA 2026 — locally-authored summary)

## Summary
Medical nutrition therapy and physical activity are cornerstones of every
diabetes treatment plan and apply regardless of pharmacotherapy.

## Medical nutrition therapy
- Refer to a registered dietitian when feasible, especially at diagnosis,
  with major treatment changes, or with complications.
- No single eating pattern is required; Mediterranean, DASH, plant-forward,
  and lower-carbohydrate patterns are all supported when they fit patient
  preference and produce sustainable weight and glycemic improvement.
- Encourage minimally processed foods and reduction in sugar-sweetened
  beverages.

## Physical activity
- At least 150 minutes per week of moderate-to-vigorous aerobic activity
  spread over three or more days, with no more than two consecutive days
  without activity.
- Resistance training on two or more days per week.
- For older adults, add balance and flexibility work two to three days per
  week.
- Reduce prolonged sitting; aim to interrupt sitting at least every 30
  minutes during waking hours.

## Sleep and behavioral
Screen for sleep disturbance, depression, and diabetes distress at least
annually. Each can derail self-management even when the medication regimen
looks right on paper.
""",
    ),
    (
        "ascvd-statin",
        "ASCVD risk and statin co-management in diabetes",
        "A",
        """# Statin Therapy in Diabetes (ADA 2026 — locally-authored summary)

## Summary
Diabetes itself is an ASCVD risk enhancer, and most adults with diabetes
qualify for statin therapy.

- Age 40 to 75 with diabetes: moderate-intensity statin in addition to
  lifestyle therapy. Use high-intensity statin in patients with multiple
  ASCVD risk factors, established ASCVD, or 10-year ASCVD risk in the
  intermediate-to-high range.
- Age younger than 40 or older than 75 with diabetes: individualize based
  on ASCVD risk factors, target organ damage, and life expectancy.
- Established ASCVD: high-intensity statin; consider adding ezetimibe and
  then a PCSK9 inhibitor if LDL-C remains above the relevant secondary-
  prevention threshold.

## Lipid monitoring
Check a lipid panel at diagnosis, at initiation or change of lipid-lowering
therapy, and at least every 4 to 12 months thereafter to assess adherence
and response.

## Co-management
Statins can produce small, generally reversible increases in fasting
glucose and A1c. The cardiovascular benefit overwhelmingly outweighs this
effect; do not discontinue a statin for this reason.
""",
    ),
    (
        "bp-targets-diabetes",
        "Hypertension targets in patients with diabetes",
        "B",
        """# Blood Pressure Targets in Diabetes (ADA 2026 — locally-authored summary)

## Summary
For most adults with diabetes and hypertension, the recommended blood
pressure target is below 130/80 mmHg, provided this can be achieved
safely. A higher individualized target (such as below 140/90 mmHg) is
appropriate for selected older adults or those at high risk of orthostasis
or falls.

## First-line agents
- ACE inhibitor or ARB is preferred when albuminuria is present or when
  there is concomitant CKD.
- Otherwise, ACE inhibitor, ARB, thiazide-like diuretic, or dihydropyridine
  calcium channel blocker are all reasonable initial agents.
- Combination therapy is usually required to reach target; consider
  starting two agents when baseline blood pressure is more than 20/10 mmHg
  above target.

## Monitoring
Confirm office readings with home blood pressure monitoring whenever
possible. Reassess medication after lifestyle changes and after each dose
titration in two to four weeks.
""",
    ),
    (
        "cgm-primary-care",
        "Continuous glucose monitoring considerations in primary care",
        "B",
        """# Continuous Glucose Monitoring in Primary Care (ADA 2026 — locally-authored summary)

## Summary
Continuous glucose monitoring (CGM) is recommended for adults with type 1
diabetes and for adults with type 2 diabetes on any insulin therapy. CGM
may also be offered to selected adults with type 2 diabetes on non-insulin
therapy when actionable insight into glycemic patterns is expected to
change management.

## Useful CGM metrics for primary care
- Time in range (typically 70 to 180 mg/dL): aim for at least 70 percent
  for most non-pregnant adults; lower targets for frail older patients.
- Time below range (below 70 mg/dL): aim for under 4 percent, and time
  below 54 mg/dL under 1 percent.
- Glucose management indicator (GMI): an estimated A1c-equivalent that can
  highlight discordance between self-measured patterns and lab A1c.

## Workflow
Pull a 14-day ambulatory glucose profile report at each visit. Adjust one
parameter at a time (basal, prandial, or lifestyle) and recheck. Reinforce
the patient's role in reviewing trends between visits, not just chasing
individual readings.
""",
    ),
]


def build_ada_2026_chunks() -> list[GuidelineChunk]:
    """Build and return all ADA 2026 locally-authored chunks.

    Used by both ``ingest`` (which persists with embeddings) and by tests /
    verifications that want chunk dicts without a corpus/embedder.
    """
    out: list[GuidelineChunk] = []
    for slug, label, grade, text in _ADA_2026_SUMMARIES:
        src = ChunkSource(
            source_id=SOURCE_ID,
            source_organization=SOURCE_ORGANIZATION,
            source_name=SOURCE_NAME,
            source_year=SOURCE_YEAR,
            recommendation_grade=grade,
            extra_meta={"source_url": SOURCE_URL, "summary_slug": slug, "summary_label": label},
        )
        chunks = chunk_text(text, src, id_prefix=f"{SOURCE_ID}-{slug}-")
        out.extend(chunks)
    return out


def ingest(corpus: Any, embedder: Any) -> int:
    """Upsert all ADA 2026 locally-authored chunks into *corpus*.

    Returns the number of chunks upserted.

    AgDR-0079: contextualization is opt-in via
    ``COPILOT_CONTEXTUAL_RETRIEVAL=1``. The source-doc text for each
    summary is reconstructed from ``_ADA_2026_SUMMARIES`` so the
    contextualization prompt has section-level grounding.
    """

    from ..contextualization import embed_and_upsert_chunks

    chunks = build_ada_2026_chunks()
    logger.info("ADA-SoC-2026: %d chunks", len(chunks))
    if not chunks:
        return 0

    # Per-chunk source-doc lookup: each chunk's id_prefix carries the
    # summary slug, so we can recover the originating summary text.
    summary_text_by_slug = {slug: text for slug, _label, _grade, text in _ADA_2026_SUMMARIES}

    def _source_doc_for(chunk: GuidelineChunk) -> str:
        slug = chunk.chunk_id.split("-")[2] if "-" in chunk.chunk_id else ""
        return summary_text_by_slug.get(slug, chunk.text)

    # Group chunks by source-doc so contextualization receives the full
    # summary (the broader the document context, the higher-quality the
    # context summary per Anthropic's published technique).
    by_doc: dict[str, list[GuidelineChunk]] = {}
    for c in chunks:
        by_doc.setdefault(_source_doc_for(c), []).append(c)

    for source_doc_text, group in by_doc.items():
        embed_and_upsert_chunks(corpus, embedder, group, source_doc_text)
    return len(chunks)
