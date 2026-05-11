"""Clinical-synonym table for query rewriting (AgDR-0085, Plan §7.2.c).

Maps a *canonical* clinical term to a list of accepted *variants* (case-
insensitive). The table is intentionally hand-curated — every entry is one
that has come up in either the bundled corpus chunks (CDC-ACIP, openFDA,
HMS-LOE, ADA 2026, ACC/AHA 2026), the Wk2 evaluation cases, or both.

Selection criteria (in priority order):
  1. The term appears in at least one corpus chunk AND in at least one
     real-world clinician question pattern from Wk1/Wk2 user research.
  2. The variants are not synonyms of one another by stem (BM25 already
     handles those) — they are spelling, abbreviation, brand/generic, or
     historical-name pairs that BM25 *cannot* bridge.
  3. The expansion does not add ambiguity — e.g., we do not map "MS" to
     {"multiple sclerosis", "morphine sulfate"} because the ambiguity
     would tank precision.

The table is small on purpose. Plan §7.2.c calls for "top-200 clinical
terms" eventually; this is the ~40-term Wk2 baseline that already covers
the load-bearing cases (HbA1c, eGFR, BP, LDL, T4/TSH, common drug
brand/generic pairs). Wk3 expansion follows the same selection criteria.

Lookup contract: callers should ``token.lower()`` before lookup. The
table itself stores lowercase canonical keys and lowercase variants.
"""

from __future__ import annotations

# Lab values + clinical abbreviations
_LAB_SYNONYMS: dict[str, list[str]] = {
    "hba1c": ["hba1c", "a1c", "hemoglobin a1c", "glycated hemoglobin", "glycohemoglobin"],
    "ldl": ["ldl", "ldl-c", "low-density lipoprotein", "ldl cholesterol"],
    "hdl": ["hdl", "hdl-c", "high-density lipoprotein", "hdl cholesterol"],
    "tg": ["tg", "triglycerides", "triglyceride"],
    "egfr": ["egfr", "estimated gfr", "estimated glomerular filtration rate", "glomerular filtration rate"],
    "cr": ["cr", "creatinine", "serum creatinine"],
    "bun": ["bun", "blood urea nitrogen", "urea nitrogen"],
    "tsh": ["tsh", "thyroid stimulating hormone", "thyrotropin"],
    "t4": ["t4", "free t4", "thyroxine", "free thyroxine"],
    "t3": ["t3", "free t3", "triiodothyronine"],
    "inr": ["inr", "international normalized ratio", "prothrombin time inr"],
    "pt": ["pt", "prothrombin time"],
    "ptt": ["ptt", "aptt", "partial thromboplastin time", "activated partial thromboplastin time"],
    "esr": ["esr", "erythrocyte sedimentation rate", "sed rate"],
    "crp": ["crp", "c-reactive protein"],
    "bp": ["bp", "blood pressure"],
    "sbp": ["sbp", "systolic blood pressure", "systolic bp"],
    "dbp": ["dbp", "diastolic blood pressure", "diastolic bp"],
    "hr": ["hr", "heart rate", "pulse"],
    "rr": ["rr", "respiratory rate"],
    "spo2": ["spo2", "oxygen saturation", "pulse oximetry", "o2 sat"],
    "bmi": ["bmi", "body mass index"],
    "cbc": ["cbc", "complete blood count"],
    "cmp": ["cmp", "comprehensive metabolic panel"],
    "bmp": ["bmp", "basic metabolic panel"],
    "ckd": ["ckd", "chronic kidney disease"],
    "ascvd": ["ascvd", "atherosclerotic cardiovascular disease"],
    "afib": ["afib", "a-fib", "atrial fibrillation"],
    "copd": ["copd", "chronic obstructive pulmonary disease"],
    "chf": ["chf", "congestive heart failure", "heart failure"],
    "dm": ["dm", "diabetes", "diabetes mellitus", "type 2 diabetes", "t2dm"],
    "htn": ["htn", "hypertension", "high blood pressure"],
    "mi": ["mi", "myocardial infarction", "heart attack"],
}

# Drug brand/generic pairs (only those that appear in the bundled corpus)
_DRUG_SYNONYMS: dict[str, list[str]] = {
    "metformin": ["metformin", "glucophage"],
    "atorvastatin": ["atorvastatin", "lipitor"],
    "rosuvastatin": ["rosuvastatin", "crestor"],
    "simvastatin": ["simvastatin", "zocor"],
    "lisinopril": ["lisinopril", "prinivil", "zestril"],
    "losartan": ["losartan", "cozaar"],
    "amlodipine": ["amlodipine", "norvasc"],
    "metoprolol": ["metoprolol", "lopressor", "toprol-xl"],
    "warfarin": ["warfarin", "coumadin", "jantoven"],
    "clopidogrel": ["clopidogrel", "plavix"],
    "omeprazole": ["omeprazole", "prilosec"],
    "pantoprazole": ["pantoprazole", "protonix"],
    "levothyroxine": ["levothyroxine", "synthroid", "levoxyl"],
    "albuterol": ["albuterol", "ventolin", "proair", "salbutamol"],
    "fluticasone": ["fluticasone", "flovent", "flonase"],
    "sertraline": ["sertraline", "zoloft"],
    "gabapentin": ["gabapentin", "neurontin"],
    "amoxicillin": ["amoxicillin", "amoxil"],
    "azithromycin": ["azithromycin", "zithromax", "z-pak"],
    "furosemide": ["furosemide", "lasix"],
    "hydrochlorothiazide": ["hydrochlorothiazide", "hctz", "microzide"],
    "prednisone": ["prednisone", "deltasone"],
    "ibuprofen": ["ibuprofen", "advil", "motrin"],
    "acetaminophen": ["acetaminophen", "tylenol", "paracetamol"],
}


def _build_lookup() -> dict[str, list[str]]:
    """Flatten the canonical → variants tables into a variant → all-variants
    lookup so any input token in the synonym universe yields the full set."""
    out: dict[str, list[str]] = {}
    for table in (_LAB_SYNONYMS, _DRUG_SYNONYMS):
        for variants in table.values():
            normalized = [v.lower() for v in variants]
            unique = list(dict.fromkeys(normalized))
            for v in unique:
                if v in out:
                    # Two canonical groups share a variant — should not happen
                    # in the curated table, but if it does, merge defensively.
                    merged = list(dict.fromkeys(out[v] + unique))
                    out[v] = merged
                else:
                    out[v] = unique
    return out


SYNONYM_LOOKUP: dict[str, list[str]] = _build_lookup()


def variants_for(token: str) -> list[str] | None:
    """Return all variants for *token* (case-insensitive) or None if the
    token is not in the table. The first element of the returned list is
    always the canonical-table order from the source dict."""
    return SYNONYM_LOOKUP.get(token.lower())
