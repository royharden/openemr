"""PHI stripping helper for RAG query sanitisation.

The supervisor calls ``strip_phi(query)`` before passing the user question
to the ``HybridRetriever`` so patient identifiers never enter retrieval logs
or corpus queries.

Anti-pattern §13: NO PHI in retrieval queries (enforced in eval via verifier
rule ``no_phi_in_logs``).

Patterns stripped
-----------------
- SSN: ``XXX-XX-XXXX`` / ``XXXXXXXXX``
- MRN-like: ``MRN:XXXXX`` or bare ``#XXXXX`` numeric IDs
- US phone: various formats
- ISO dates that could be DOB: ``YYYY-MM-DD``
- US dates: ``MM/DD/YYYY`` / ``MM-DD-YYYY``
- Email addresses
- Name-like capitalized phrases following common introducing words
"""

from __future__ import annotations

import re

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
_MRN_RE = re.compile(r"\bMRN\s*:?\s*\d+\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_US_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_NAME_INTRO_RE = re.compile(
    r"(?:patient|pt\.?|mr\.?|mrs\.?|ms\.?|dr\.?)\s+[A-Z][a-z]+"
    r"(?:\s+[A-Z][a-z]+)?",
    re.IGNORECASE,
)

_PLACEHOLDER = "[REDACTED]"


def strip_phi(query: str) -> str:
    """Return *query* with PHI patterns replaced by ``[REDACTED]``.

    Designed for retrieval query sanitisation — not a HIPAA de-identification
    tool.  Clinical question words (drug names, lab names) are preserved.
    """
    q = _SSN_RE.sub(_PLACEHOLDER, query)
    q = _MRN_RE.sub(_PLACEHOLDER, q)
    q = _PHONE_RE.sub(_PLACEHOLDER, q)
    q = _ISO_DATE_RE.sub(_PLACEHOLDER, q)
    q = _US_DATE_RE.sub(_PLACEHOLDER, q)
    q = _EMAIL_RE.sub(_PLACEHOLDER, q)
    q = _NAME_INTRO_RE.sub(_PLACEHOLDER, q)
    return q
