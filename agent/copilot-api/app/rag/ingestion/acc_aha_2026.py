"""ACC/AHA 2026 Dyslipidemia Guideline — locally-authored summaries.

Copyright posture
-----------------
The official ACC/AHA 2026 Dyslipidemia Guideline is a copyrighted
publication.  This module commits **no copyrighted guideline body text**.
Each chunk below is an *original summary* of a recommendation written in
the primary-care educator's own words.  The canonical source URL is
recorded in ``source_url`` metadata only; the chunk text never reproduces
guideline prose.  See Plan §6.4 (copyright guard requirement).

Authoring rule of thumb (Plan §6.4):
  - Never paraphrase >30 consecutive words of guideline body text.
  - Describe each recommendation in plain language for PCPs.
  - The official URL goes in source_url metadata, not in chunk text.

Source metadata
---------------
source_id            : ACC-AHA-Lipid-2026
source_organization  : ACC-AHA
source_name          : ACC/AHA 2026 Dyslipidemia Guideline
source_year          : 2026
source_url           : https://www.acc.org/about-acc/press-releases/2026/03/13/18/01/accaha-issue-updated-guideline-for-managing-lipids-cholesterol
recommendation_grade : per chunk, ACC/AHA "COR/LOE" shape, compact form
                       (e.g. "I/A", "IIa/B", "III/B").  Field max length is
                       8 chars in the locked contract; longer suffixes
                       (B-R, B-NR) are abbreviated to fit.
"""

from __future__ import annotations

import logging
from typing import Any

from ..chunker import ChunkSource, chunk_text
from ..contracts import GuidelineChunk

logger = logging.getLogger(__name__)

SOURCE_ID = "ACC-AHA-Lipid-2026"
SOURCE_ORGANIZATION = "ACC-AHA"
SOURCE_NAME = "ACC/AHA 2026 Dyslipidemia Guideline"
SOURCE_YEAR = 2026
SOURCE_URL = (
    "https://www.acc.org/about-acc/press-releases/2026/03/13/18/01/"
    "accaha-issue-updated-guideline-for-managing-lipids-cholesterol"
)

# Plan §6.4 + AgDR-0070 — distinctive verbatim phrases from the official
# ACC/AHA Dyslipidemia Guideline. The `--check-corpus-copyright` scan trips
# on any chunk text containing these substrings (case-insensitive). The
# class+level pattern is the ACC/AHA recommendation grammar — only ever
# appears in the official publication. Authoring rule: locally-authored
# summaries paraphrase recommendations in plain English without using the
# Class N / Level of Evidence X cadence.
COPYRIGHT_TRIP_PHRASES: list[str] = [
    # The Class/Level pattern is uniquely ACC/AHA recommendation-table prose.
    "Class I Recommendation",
    "Class IIa Recommendation",
    "Class IIb Recommendation",
    "Class III: No Benefit",
    "Class III: Harm",
    "Level of Evidence: A",
    "Level of Evidence: B-R",
    "Level of Evidence: B-NR",
    "Level of Evidence: C-LD",
    "Level of Evidence: C-EO",
    # Distinctive citation-block phrasings that would only appear if someone
    # copy-pasted from the official guideline.
    "[ACC/AHA recommendation]",
    "Journal of the American College of Cardiology 2026;",
]


# ---------------------------------------------------------------------------
# Locally-authored summaries (original phrasing only — NO copyrighted text).
# Each entry: (chunk_slug, short_label, cor_loe, summary_text)
# ---------------------------------------------------------------------------
_ACC_AHA_2026_SUMMARIES: list[tuple[str, str, str | None, str]] = [
    (
        "ldl-primary-prevention-risk",
        "LDL-C goals in primary prevention by 10-year ASCVD risk",
        "I/A",
        """# Primary-Prevention LDL Targets by Risk Tier (ACC/AHA 2026 — locally-authored summary)

## Summary
In adults without established atherosclerotic cardiovascular disease,
LDL-C goals are stratified by calculated 10-year ASCVD risk:

- Low risk (under 5 percent): emphasize lifestyle; consider statin only
  with strong risk enhancers or a coronary calcium score above 100.
- Borderline risk (5 to 7.5 percent): shared decision-making; LDL-C goal
  generally below 130 mg/dL with lifestyle first, statin if enhancers or a
  positive coronary calcium score.
- Intermediate risk (7.5 to 20 percent): moderate-intensity statin to
  reduce LDL-C by at least 30 percent; aim for LDL-C below 100 mg/dL.
- High risk (20 percent or higher): high-intensity statin to reduce LDL-C
  by 50 percent or more; aim for LDL-C below 70 mg/dL.

## Risk enhancers that move treatment intensity up
Family history of premature ASCVD, chronic kidney disease, persistent
elevation of LDL-C above 160 mg/dL, metabolic syndrome, inflammatory
conditions, South Asian ancestry, persistently elevated triglycerides, and
elevated lipoprotein(a) or apolipoprotein B.
""",
    ),
    (
        "ldl-secondary-prevention",
        "LDL-C goals in secondary prevention",
        "I/A",
        """# Secondary-Prevention LDL Targets (ACC/AHA 2026 — locally-authored summary)

## Summary
For adults with established atherosclerotic cardiovascular disease (prior
MI, ischemic stroke, symptomatic peripheral arterial disease, or coronary
revascularization), the LDL-C goal is below 70 mg/dL. For very-high-risk
patients (multiple major ASCVD events, or one major event plus multiple
high-risk conditions such as diabetes, CKD, or persistent hypertension),
the goal is below 55 mg/dL.

## Treatment approach
Start with maximally tolerated high-intensity statin. If the LDL-C goal is
not met, add ezetimibe. If the goal is still not met, add a PCSK9 inhibitor
(or, where appropriate, bempedoic acid or inclisiran). Repeat the lipid
panel 4 to 12 weeks after each change and at least annually once stable.
""",
    ),
    (
        "high-intensity-statin",
        "High-intensity statin definition and indications",
        "I/A",
        """# High-Intensity Statin Therapy (ACC/AHA 2026 — locally-authored summary)

## Summary
High-intensity statin therapy is defined as a regimen expected to lower
LDL-C by at least 50 percent. The qualifying regimens are atorvastatin 40
or 80 mg daily and rosuvastatin 20 or 40 mg daily.

## Indications
- All adults with established ASCVD when tolerated.
- Adults aged 40 to 75 with diabetes and at least one ASCVD risk enhancer.
- Adults aged 40 to 75 with primary prevention and 10-year ASCVD risk at
  or above 20 percent.
- Adults with LDL-C at or above 190 mg/dL (suspected familial
  hypercholesterolemia phenotype), regardless of calculated risk.

## Adherence and tolerance
Confirm tolerance and adherence before declaring statin intolerance.
Address muscle symptoms with the standard re-challenge approach (covered
in a separate summary).
""",
    ),
    (
        "moderate-intensity-statin",
        "Moderate-intensity statin definition and indications",
        "I/A",
        """# Moderate-Intensity Statin Therapy (ACC/AHA 2026 — locally-authored summary)

## Summary
Moderate-intensity statin therapy is defined as a regimen expected to
lower LDL-C by 30 to 49 percent. Qualifying regimens include atorvastatin
10 or 20 mg, rosuvastatin 5 or 10 mg, simvastatin 20 or 40 mg,
pravastatin 40 or 80 mg, lovastatin 40 mg, fluvastatin XL 80 mg, and
pitavastatin 1 to 4 mg.

## Indications
- Adults aged 40 to 75 with diabetes without ASCVD risk enhancers.
- Adults aged 40 to 75 with 10-year ASCVD risk in the intermediate range
  (7.5 to less than 20 percent) who do not warrant high-intensity therapy.
- Adults aged 75 and older as part of shared decision-making for primary
  prevention.

## Switching considerations
Patients on simvastatin 80 mg should be transitioned to an alternative
high- or moderate-intensity statin due to muscle-toxicity risk at the
80 mg dose.
""",
    ),
    (
        "ezetimibe-addon",
        "Ezetimibe add-on indications",
        "I/B",
        """# Ezetimibe as Add-On Therapy (ACC/AHA 2026 — locally-authored summary)

## Summary
Ezetimibe 10 mg daily is the first non-statin add-on for patients who do
not reach LDL-C goal on maximally tolerated statin therapy. Typical
incremental LDL-C reduction is about 15 to 25 percent on top of statin.

## Indications
- Secondary prevention: ezetimibe is added when LDL-C remains above the
  secondary-prevention threshold despite maximally tolerated statin.
- Primary prevention high-risk: ezetimibe may be added when LDL-C remains
  above goal after high-intensity statin.
- Statin-intolerant patients: ezetimibe is a reasonable first step at lower
  cost than PCSK9 inhibitors or bempedoic acid.

## Practical notes
Generic and inexpensive. Well tolerated. No required laboratory monitoring
beyond the periodic lipid panel.
""",
    ),
    (
        "pcsk9-inhibitor",
        "PCSK9 inhibitor indications and access",
        "IIa/A",
        """# PCSK9 Inhibitors (ACC/AHA 2026 — locally-authored summary)

## Summary
PCSK9 monoclonal antibodies (alirocumab, evolocumab) lower LDL-C by an
additional 50 to 60 percent on top of statin plus ezetimibe. Inclisiran, a
small-interfering-RNA PCSK9 modulator, is dosed twice yearly after a
loading regimen and produces similar magnitude reductions.

## Indications
- Very-high-risk secondary prevention with LDL-C remaining above 55 mg/dL
  despite maximally tolerated statin plus ezetimibe.
- Familial hypercholesterolemia with LDL-C remaining above 70 mg/dL on
  maximally tolerated oral therapy.
- Statin intolerance with persistently elevated LDL-C after lifestyle and
  non-statin oral options.

## Access considerations
Specialty pharmacy and prior authorization are typically required. Plan
ahead and document failure of, or intolerance to, prior therapies.
Patient-assistance programs are available for both manufacturers and can
materially reduce out-of-pocket cost.
""",
    ),
    (
        "bempedoic-acid",
        "Bempedoic acid for statin-intolerant patients",
        "IIa/B",
        """# Bempedoic Acid (ACC/AHA 2026 — locally-authored summary)

## Summary
Bempedoic acid 180 mg daily is an oral non-statin lipid-lowering option,
typically combined with ezetimibe for additive LDL-C reduction of about 20
to 25 percent. It is most useful in patients who cannot tolerate statins
or who have not reached LDL-C goal on statin plus ezetimibe.

## Indications
- Statin-intolerant adults with elevated LDL-C and high ASCVD risk.
- Adjunct in secondary prevention when LDL-C remains above goal on statin
  plus ezetimibe and a PCSK9 inhibitor is not feasible.

## Safety
Modest increases in serum uric acid have been observed; consider gout risk
in selected patients. Less muscle toxicity than statins because the drug is
activated only in the liver.
""",
    ),
    (
        "triglycerides-icosapent",
        "Triglyceride thresholds and icosapent ethyl",
        "IIa/B",
        """# Triglyceride Management (ACC/AHA 2026 — locally-authored summary)

## Summary
Fasting triglycerides at or above 500 mg/dL warrant pharmacotherapy to
reduce pancreatitis risk, in addition to lifestyle modification (alcohol
reduction, weight loss, glycemic control, treatment of secondary causes
such as hypothyroidism). Triglycerides between 150 and 499 mg/dL are
addressed primarily by treating the underlying cause and by statin
therapy when ASCVD risk is elevated.

## Icosapent ethyl
For adults with established ASCVD or diabetes plus risk enhancers who
have triglycerides between roughly 135 and 499 mg/dL despite maximally
tolerated statin, icosapent ethyl 2 grams twice daily reduces residual
ASCVD events.

## Other options
Fibrates (fenofibrate) are reserved for triglycerides at or above 500
mg/dL to reduce pancreatitis risk; the residual ASCVD benefit of fibrates
on top of statin is modest. Niacin is not recommended for ASCVD-event
reduction.
""",
    ),
    (
        "lipoprotein-a-testing",
        "Lipoprotein(a) testing recommendations",
        "IIa/B",
        """# Lipoprotein(a) Testing (ACC/AHA 2026 — locally-authored summary)

## Summary
A one-time measurement of lipoprotein(a) is reasonable in most adults to
refine ASCVD risk, and is particularly useful in:

- Adults with a family history of premature ASCVD.
- Adults with personal premature ASCVD not explained by other risk
  factors.
- Borderline or intermediate calculated 10-year ASCVD risk where the
  decision between lifestyle alone and statin therapy is unclear.

## Interpretation
A lipoprotein(a) above 50 mg/dL (or above 125 nmol/L, depending on the
assay) is considered a risk enhancer and supports more intensive LDL-C
management. Levels are largely genetically determined and do not need
repeat measurement in most patients.

## Treatment implications today
There is no FDA-approved drug that lowers lipoprotein(a) with proven
outcome benefit at the time of this guideline; the result is used to
intensify LDL-C-lowering therapy rather than to target lipoprotein(a)
itself.
""",
    ),
    (
        "statin-safety",
        "Statin safety: muscle, liver, interactions",
        "I/B",
        """# Statin Safety Monitoring (ACC/AHA 2026 — locally-authored summary)

## Summary
Statins are generally well tolerated. Routine creatine kinase and liver
enzyme monitoring is not required in asymptomatic patients; check at
baseline and then only when clinically indicated.

## Muscle symptoms
- Most muscle complaints attributed to statins are non-specific.
- A standard re-challenge approach is recommended: hold the statin, allow
  symptoms to resolve, then restart the same statin at a lower dose or
  switch to a different statin (often hydrophilic options such as
  pravastatin or rosuvastatin every other day).
- Measure CK if pain is severe, accompanied by weakness, or associated
  with dark urine.
- True statin-associated rhabdomyolysis is rare.

## Liver enzymes
Modest, transient transaminase elevations are common and do not require
discontinuation unless they exceed three times the upper limit of normal
and are confirmed on repeat testing.

## Drug interactions
- Simvastatin and lovastatin: extensive CYP3A4 interactions; avoid with
  strong CYP3A4 inhibitors (clarithromycin, itraconazole, HIV protease
  inhibitors).
- Concomitant amiodarone, verapamil, or diltiazem requires simvastatin
  dose limits.
- Rosuvastatin and atorvastatin have fewer CYP3A4 interactions and are
  preferred when interaction risk is a concern.
""",
    ),
]


def build_acc_aha_2026_chunks() -> list[GuidelineChunk]:
    """Build and return all ACC/AHA 2026 locally-authored chunks."""
    out: list[GuidelineChunk] = []
    for slug, label, grade, text in _ACC_AHA_2026_SUMMARIES:
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
    """Upsert all ACC/AHA 2026 locally-authored chunks into *corpus*."""
    chunks = build_acc_aha_2026_chunks()
    logger.info("ACC-AHA-Lipid-2026: %d chunks", len(chunks))
    if not chunks:
        return 0
    embeddings = embedder.embed([c.text for c in chunks])
    for chunk, embedding in zip(chunks, embeddings):
        corpus.upsert_chunk(chunk, embedding)
    return len(chunks)
