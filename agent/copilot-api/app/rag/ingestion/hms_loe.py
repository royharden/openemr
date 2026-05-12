"""HMS Library of Evidence (HMS-LOE) corpus ingestor.

Source
------
The HMS Library of Evidence provides curated clinical decision support
summaries with Oxford Centre for Evidence-Based Medicine (CEBM) levels.
This ingestor uses a curated subset of evidence summaries relevant to
primary care practice.

Since HMS-LOE does not offer a public REST API, we bundle a curated static
corpus of evidence summaries.  These summaries are paraphrased from
publicly-available evidence synthesis resources (UpToDate® summary
reproductions are excluded; content is derived from publicly-indexed
systematic reviews and clinical guidelines).

Grading
-------
HMS-LOE summaries use Oxford CEBM levels (1a, 1b, 2a, 2b, 3a, 3b, 4, 5).
The recommendation_grade field carries the CEBM level.

Content categories:
  - Diabetes management (metformin, insulin, A1c targets)
  - Hypertension (ACE inhibitors, ARBs, thiazides, CCBs)
  - Hyperlipidemia (statins, LDL targets)
  - Anticoagulation (warfarin, INR management)
  - Asthma / COPD (albuterol, ICS step therapy)
  - Immunization (catch-up, special populations)
  - Cancer screening (deferring USPSTF specifics to Wk3)
"""

from __future__ import annotations

import logging
from typing import Any

from ..chunker import ChunkSource, chunk_text
from ..contracts import GuidelineChunk

logger = logging.getLogger(__name__)

SOURCE_ORGANIZATION = "HMS-LOE"


# ---------------------------------------------------------------------------
# Curated evidence summaries (paraphrased from public systematic reviews).
# Each entry: (source_id, source_name, year, cebm_level, text)
# ---------------------------------------------------------------------------
_HMS_LOE_CORPUS: list[tuple[str, str, int, str | None, str]] = [
    (
        "hms-loe-metformin-renal",
        "HMS-LOE: Metformin in Chronic Kidney Disease",
        2022,
        "1a",
        """# Metformin Use in Chronic Kidney Disease

## Summary (Oxford CEBM Level 1a)
Metformin is contraindicated when eGFR falls below 30 mL/min/1.73 m².
When eGFR is 30–44 mL/min/1.73 m², metformin may be continued with increased
monitoring (check eGFR every 3 months) and dose reduction.

## Dosing Guidance
- eGFR ≥ 45: No restriction; continue standard dosing.
- eGFR 30–44: Use with caution; consider dose reduction to 50%.
- eGFR < 30: Contraindicated.
- Acute illness with dehydration risk: Hold metformin temporarily.

## Rationale
Metformin is renally cleared and accumulates in renal impairment,
increasing risk of lactic acidosis. The FDA updated the label in 2016
to allow use down to eGFR 30 with appropriate monitoring.

## Key References
FDA Drug Safety Communication 2016; ADA Standards of Medical Care 2024;
NICE NG28 Type 2 Diabetes 2022.
""",
    ),
    (
        "hms-loe-a1c-targets",
        "HMS-LOE: HbA1c Targets in Type 2 Diabetes",
        2023,
        "1a",
        """# HbA1c Targets in Type 2 Diabetes

## Summary (Oxford CEBM Level 1a)
For most non-pregnant adults with type 2 diabetes, an HbA1c target of less
than 7.0% (53 mmol/mol) is recommended. A less stringent target (< 8.0%) is
appropriate for patients with limited life expectancy, advanced complications,
or high hypoglycemia risk.

## Individualised Targets
- Healthy adults, long life expectancy: < 6.5–7.0%.
- Most adults: < 7.0%.
- Older adults with comorbidities or high hypoglycemia risk: < 7.5–8.0%.
- Very frail / end-stage disease: < 8.5% (avoid hypoglycemia).

## Monitoring
Check HbA1c every 3 months until target achieved, then every 6 months.

## References
ADA Standards of Medical Care 2024; EASD/ADA Consensus Report 2022;
NICE NG28 2022.
""",
    ),
    (
        "hms-loe-statin-ldl",
        "HMS-LOE: Statin Therapy and LDL Targets",
        2023,
        "1a",
        """# Statin Therapy and LDL-C Targets

## Summary (Oxford CEBM Level 1a)
Statin therapy reduces ASCVD risk proportionally to LDL-C reduction.
High-intensity statins (atorvastatin 40–80 mg, rosuvastatin 20–40 mg) are
preferred for secondary prevention and high-risk primary prevention.

## LDL-C Goals
- Secondary prevention (established ASCVD): < 70 mg/dL; < 55 mg/dL for very
  high-risk patients (ACC/AHA 2022).
- Primary prevention, high risk (10-year ASCVD risk ≥ 7.5%): < 70 mg/dL.
- Primary prevention, intermediate risk (5–7.5%): < 100 mg/dL.

## Drug Interactions
Simvastatin has multiple CYP3A4 interactions; atorvastatin and rosuvastatin
are preferred. Avoid simvastatin > 20 mg with amlodipine.

## References
ACC/AHA 2018 Cholesterol Guidelines; AHA/ACC 2022 Update.
""",
    ),
    (
        "hms-loe-hypertension-bp-targets",
        "HMS-LOE: Blood Pressure Targets in Hypertension",
        2023,
        "1a",
        """# Blood Pressure Targets in Hypertension

## Summary (Oxford CEBM Level 1a)
For most adults with confirmed hypertension, a blood pressure target of
< 130/80 mmHg is recommended (ACC/AHA 2017 guideline).

## Population-specific Targets
- General adults: < 130/80 mmHg.
- Adults ≥ 65 years (community-dwelling): < 130/80 mmHg (SPRINT trial evidence).
- Adults with CKD: < 130/80 mmHg.
- Adults with diabetes: < 130/80 mmHg.
- Frail older adults: individualised; < 150/90 mmHg acceptable.

## First-line Agents
Thiazide diuretics, ACE inhibitors, ARBs, and CCBs are all first-line.
ACE inhibitors or ARBs are preferred in CKD with proteinuria and in diabetes.

## References
ACC/AHA 2017 Hypertension Guideline; JNC 8 (2014); ADA Standards 2024.
""",
    ),
    (
        "hms-loe-warfarin-inr",
        "HMS-LOE: Warfarin Dosing and INR Management",
        2022,
        "1b",
        """# Warfarin Dosing and INR Management

## Summary (Oxford CEBM Level 1b)
Warfarin (target INR 2.0–3.0 for most indications; 2.5–3.5 for mechanical
mitral valves) requires frequent monitoring and dose adjustment.

## Common Indications and INR Targets
- AF (non-valvular): INR 2.0–3.0.
- DVT/PE treatment: INR 2.0–3.0.
- Mechanical aortic valve: INR 2.0–3.0.
- Mechanical mitral valve: INR 2.5–3.5.

## Dose Adjustment Approach
- INR < 2.0 (subtherapeutic): increase weekly dose by 10–15%.
- INR 3.1–3.5: reduce weekly dose by 10%.
- INR > 4.0 without bleeding: hold 1–2 doses, recheck in 1–2 days.
- INR > 10 or major bleeding: vitamin K IV ± 4-factor PCC.

## Key Drug Interactions
Amiodarone, fluconazole, TMP-SMX significantly increase INR.
Rifampin, carbamazepine, St. John's Wort decrease INR.
Monitor closely with any new medication.

## References
CHEST Antithrombotic Therapy Guidelines 2021; ACC/AHA Afib Guidelines 2023.
""",
    ),
    (
        "hms-loe-asthma-step-therapy",
        "HMS-LOE: Asthma Step Therapy",
        2023,
        "1a",
        """# Asthma Step Therapy

## Summary (Oxford CEBM Level 1a)
Asthma management uses a stepwise approach guided by symptom control and
future risk (GINA 2024).

## GINA Steps
- Step 1: SABA PRN (mild intermittent) or low-dose ICS-formoterol PRN.
- Step 2: Low-dose daily ICS + SABA PRN.
- Step 3: Low-dose ICS-LABA + SABA PRN, or medium-dose ICS.
- Step 4: Medium-dose ICS-LABA + SABA PRN; consider LTRA or tiotropium.
- Step 5: High-dose ICS-LABA; add-on tiotropium, biologic (dupilumab,
  benralizumab, mepolizumab) for severe uncontrolled.

## Albuterol (SABA) Use
Frequent SABA use (> 2 days/week) indicates uncontrolled asthma and need
to step up controller therapy. Using SABA > 3 canisters/year is associated
with increased exacerbation risk.

## Spacer Use
Use a spacer/valved holding chamber with pMDI for optimal drug delivery.

## References
GINA Global Strategy for Asthma 2024; NAEPP EPR-4 (pending publication).
""",
    ),
    (
        "hms-loe-ace-inhibitor-cough",
        "HMS-LOE: ACE Inhibitor Cough and ARB Switch",
        2021,
        "1a",
        """# ACE Inhibitor-Induced Cough and ARB Switch

## Summary (Oxford CEBM Level 1a)
Dry, persistent cough occurs in 5–20% of patients on ACE inhibitors
(higher prevalence in East Asian populations, ~35%).
Bradykinin accumulation is the mechanism.

## Management
- Confirm cough is due to ACE inhibitor (resolves within 1–4 weeks of stopping).
- Switch to an ARB (e.g., losartan, valsartan) — equivalent BP and
  cardioprotective efficacy, no cough.
- Do not rechallenge with a different ACE inhibitor (class effect).

## Clinical Note
ARBs do not cause bradykinin accumulation; angioedema risk is far lower than
with ACE inhibitors but still possible.

## References
Cochrane Review: ACE inhibitor cough 2022; JNC 8 2014.
""",
    ),
    (
        "hms-loe-immunization-catch-up",
        "HMS-LOE: Adult Immunization Catch-up Principles",
        2024,
        "1b",
        """# Adult Immunization Catch-up Principles

## Summary (Oxford CEBM Level 1b)
Adults with incomplete or unknown vaccination history should receive catch-up
vaccination according to the ACIP adult schedule.

## Key Principles
- Vaccine series need not be restarted if there was a lapse in schedule.
- Minimum intervals between doses must be observed.
- Simultaneous administration of multiple vaccines is generally safe.

## Common Catch-up Situations
- No record of childhood vaccines: assume unvaccinated; start series.
- MMR: 2-dose series if no evidence of immunity; 1 dose if born before 1957.
- Varicella: 2-dose series if no evidence of immunity or prior disease.
- Tdap: 1 dose if never received as adult; Td booster every 10 years.
- HepB: 3-dose series if unvaccinated (or 2-dose Heplisav-B).
- Pneumococcal: see age- and risk-group recommendations.

## Documentation
Provide a vaccine information statement (VIS) before each dose.
Document in immunization information system (IIS).

## References
CDC ACIP Adult Schedule 2024; CDC General Recommendations 2011.
""",
    ),
    (
        "hms-loe-chronic-pain-nsaids",
        "HMS-LOE: Chronic Pain and NSAID Use",
        2022,
        "1a",
        """# Chronic Pain Management and NSAID Safety

## Summary (Oxford CEBM Level 1a)
NSAIDs are effective for acute and chronic musculoskeletal pain but carry
GI, cardiovascular, and renal risks that increase with age and duration.

## Risk Mitigation
- Use the lowest effective dose for the shortest duration.
- Add PPI (e.g., omeprazole 20 mg) for patients with GI risk factors
  (history of PUD, age > 60, concomitant steroids/anticoagulants).
- Avoid NSAIDs in CKD (eGFR < 30) — nephrotoxic.
- Avoid NSAIDs in heart failure — worsen fluid retention.
- Celecoxib (COX-2 selective) has lower GI risk but similar CV risk.

## Acetaminophen Alternative
Acetaminophen 325–500 mg q4–6h (max 3 g/day in elderly or hepatic impairment)
is preferred for musculoskeletal pain in high-risk patients.

## References
ACR Osteoarthritis Guidelines 2019; NICE NG59 2016.
""",
    ),
    (
        "hms-loe-copd-spirometry",
        "HMS-LOE: COPD Diagnosis and GOLD Staging",
        2023,
        "1a",
        """# COPD Diagnosis and GOLD Staging

## Summary (Oxford CEBM Level 1a)
COPD diagnosis requires spirometry: post-bronchodilator FEV1/FVC < 0.70.

## GOLD Stages
- GOLD 1 (mild): FEV1 ≥ 80% predicted.
- GOLD 2 (moderate): 50% ≤ FEV1 < 80%.
- GOLD 3 (severe): 30% ≤ FEV1 < 50%.
- GOLD 4 (very severe): FEV1 < 30%.

## Initial Pharmacotherapy (GOLD 2024)
- Group A (low symptoms, low risk): SABA or LAMA PRN.
- Group B (high symptoms, low risk): LAMA.
- Group E (high exacerbation risk): LAMA + LABA or LAMA + LABA + ICS.

## Smoking Cessation
The single most effective intervention to slow COPD progression.
Offer pharmacotherapy (varenicline, bupropion, NRT) + counseling.

## References
GOLD 2024 Report; NICE NG115 2019.
""",
    ),
]


def ingest(corpus: Any, embedder: Any) -> int:
    """Upsert all HMS-LOE curated chunks into *corpus*."""
    total = 0
    for source_id, source_name, year, grade, text in _HMS_LOE_CORPUS:
        src = ChunkSource(
            source_id=source_id,
            source_organization=SOURCE_ORGANIZATION,
            source_name=source_name,
            source_year=year,
            recommendation_grade=grade,
        )
        chunks = chunk_text(text, src, id_prefix=f"{source_id}-")
        logger.info("HMS-LOE %s: %d chunks", source_id, len(chunks))
        if not chunks:
            continue
        # AgDR-0079: pass the per-summary text as the doc context for
        # opt-in Anthropic Contextual Retrieval.
        from ..contextualization import embed_and_upsert_chunks
        embed_and_upsert_chunks(corpus, embedder, chunks, text)
        total += len(chunks)
    return total
