"""Python mirror of the PHP `QuestionRouter` for offline evaluation.

The authoritative router lives in PHP because it runs in the OpenEMR gateway.
This module mirrors the same precedence and family list so the eval suite can
assert routing decisions without spinning up Apache. KEEP THIS IN SYNC with
`interface/modules/custom_modules/oe-module-clinical-copilot/src/Gateway/QuestionRouter.php`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


FAMILY_MEDICATION = "medication"
FAMILY_ALLERGY = "allergy"
FAMILY_LABS = "labs"
FAMILY_IMMUNIZATION = "immunization"
FAMILY_WHAT_CHANGED = "what_changed"
FAMILY_IDENTITY = "identity"
FAMILY_FALLBACK = "fallback_chart_question"
FAMILY_REFUSE_CLINICAL_ACTION = "refuse_clinical_action"
FAMILY_REFUSE_OTHER_PATIENT = "refuse_other_patient"

BUILDERS_FULL = ["identity", "problems", "meds", "allergies", "labs", "immunizations"]

_OTHER_PATIENT_PATTERNS = [
    re.compile(r"\b(other|another)\s+patient\b"),
    re.compile(r"\bpatient\s+[a-z]+\s+[a-z]+\b"),
    re.compile(
        r"\b(?:john|jane|mary|robert|maria)\s+(?:smith|doe|jones|garcia|brown)\b"
    ),
]

_CLINICAL_ACTION_NEEDLES = [
    "should i ", "should we ", "recommend", "prescribe", "order ", "diagnose",
    "start her on", "start him on", "stop ", "discontinue", "increase",
    "decrease", "taper",
]

_TOPICAL = [
    (FAMILY_ALLERGY, ["allergy", "allergic", "reaction to", "penicillin", "nkda"],
     ["identity", "allergies", "meds"]),
    (FAMILY_IMMUNIZATION, [
        "vaccine", "vaccination", "shot", "immuniz", "tetanus",
        "pneumococcal", "flu shot", "covid shot",
    ], ["identity", "immunizations"]),
    (FAMILY_LABS, [
        "lab", "a1c", "ldl", "hdl", "creatinine", "abnormal",
        "result", "value", "panel", "cbc", "tsh",
    ], ["identity", "problems", "labs"]),
    (FAMILY_MEDICATION, [
        "metformin", "lisinopril", "dose", "dosage", "refill", "fill",
        "adherence", "medication", " med ", " meds", "pill", "rx",
    ], ["identity", "meds", "allergies"]),
    (FAMILY_WHAT_CHANGED, [
        "changed", "new since", "last visit", "since march",
        "since april", "anything new", "what has changed", "whats new",
    ], list(BUILDERS_FULL)),
    (FAMILY_IDENTITY, [
        "age", "sex", "name", "dob", "date of birth", "gender",
    ], ["identity"]),
]

_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class RouterDecision:
    family: str
    builders: list[str]
    refusal_reason: str | None


def normalize(question: str) -> str:
    q = _CONTROL_RE.sub("", question or "")
    q = _WS_RE.sub(" ", q)
    return q.strip()[:500]


def classify(normalized_question: str) -> RouterDecision:
    q = normalized_question.lower()
    if not q:
        return RouterDecision(FAMILY_FALLBACK, list(BUILDERS_FULL), "empty_question")

    for pattern in _OTHER_PATIENT_PATTERNS:
        if pattern.search(q):
            return RouterDecision(FAMILY_REFUSE_OTHER_PATIENT, [], "other_patient_request")

    for needle in _CLINICAL_ACTION_NEEDLES:
        if needle in q:
            return RouterDecision(
                FAMILY_REFUSE_CLINICAL_ACTION, [], "clinical_action_out_of_scope"
            )

    for family, needles, builders in _TOPICAL:
        for needle in needles:
            if needle in q:
                return RouterDecision(family, list(builders), None)

    return RouterDecision(FAMILY_FALLBACK, list(BUILDERS_FULL), None)
