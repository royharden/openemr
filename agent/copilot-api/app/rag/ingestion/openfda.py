"""OpenFDA drug label corpus ingestor.

Source
------
openFDA drug label API at https://api.fda.gov/drug/label.json
API key in OPENFDA_API_KEY (raises rate limit to 240/min × 120k/day).

The 25 high-frequency primary-care drugs below were selected based on:
  - NCHS 2022 most-prescribed drug list
  - Alignment with the Wk1 demo patient chart (metformin, lisinopril, atorvastatin)
  - Coverage of key PCP counseling topics (anticoagulants, inhalers, statins,
    diabetes, blood pressure, thyroid, antibiotics, pain management)

Drug list (documented here per plan §6 Workstream B "document it in scripts/build_corpus.py"):
  1.  metformin          — antidiabetic (biguanide)
  2.  lisinopril         — ACE inhibitor / antihypertensive
  3.  atorvastatin       — statin / hyperlipidemia
  4.  amlodipine         — CCB / antihypertensive
  5.  omeprazole         — PPI / GERD
  6.  levothyroxine      — thyroid hormone replacement
  7.  metoprolol         — beta-blocker / antihypertensive
  8.  losartan           — ARB / antihypertensive
  9.  albuterol          — SABA / asthma/COPD
 10.  simvastatin        — statin (legacy, high interaction risk)
 11.  gabapentin         — neuropathic pain / anticonvulsant
 12.  sertraline         — SSRI / depression
 13.  amoxicillin        — penicillin antibiotic
 14.  azithromycin       — macrolide antibiotic
 15.  warfarin           — anticoagulant (narrow TI)
 16.  hydrochlorothiazide — thiazide diuretic
 17.  furosemide         — loop diuretic
 18.  clopidogrel        — antiplatelet
 19.  fluticasone        — inhaled corticosteroid
 20.  rosuvastatin       — statin
 21.  prednisone         — oral corticosteroid
 22.  ibuprofen          — NSAID / pain
 23.  acetaminophen      — analgesic / antipyretic
 24.  insulin glargine   — basal insulin
 25.  pantoprazole       — PPI (alternative to omeprazole)

Grading
-------
FDA drug labels do not carry ACIP/USPSTF recommendation grades.
``recommendation_grade`` is set to ``None`` for all openFDA chunks.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from ..chunker import ChunkSource, chunk_text
from ..contracts import GuidelineChunk

logger = logging.getLogger(__name__)

SOURCE_ORGANIZATION = "FDA"

# The 25 high-frequency PCP drugs (generic names as openFDA search terms).
DRUG_LIST: list[str] = [
    "metformin",
    "lisinopril",
    "atorvastatin",
    "amlodipine",
    "omeprazole",
    "levothyroxine",
    "metoprolol",
    "losartan",
    "albuterol",
    "simvastatin",
    "gabapentin",
    "sertraline",
    "amoxicillin",
    "azithromycin",
    "warfarin",
    "hydrochlorothiazide",
    "furosemide",
    "clopidogrel",
    "fluticasone",
    "rosuvastatin",
    "prednisone",
    "ibuprofen",
    "acetaminophen",
    "insulin glargine",
    "pantoprazole",
]

_OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
# Sections of the label we extract as chunks.  Each section becomes a separate
# GuidelineChunk so retrieval can surface the specific sub-section.
_LABEL_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "warnings_and_cautions",
    "contraindications",
    "drug_interactions",
    "use_in_specific_populations",
    "clinical_pharmacology",
    "adverse_reactions",
]


def ingest(corpus: Any, embedder: Any) -> int:
    """Fetch openFDA labels for the 25 drugs and upsert chunks."""
    api_key = os.environ.get("OPENFDA_API_KEY", "")
    total = 0
    for drug in DRUG_LIST:
        label = _fetch_label(drug, api_key)
        if label is None:
            logger.warning("No label found for %s — skipping", drug)
            continue
        source_name = _get_brand_generic(label, drug)
        source_year = _get_label_year(label)
        source_id = f"openfda-{drug.replace(' ', '-').replace('/', '-')}"

        for section_key in _LABEL_SECTIONS:
            section_text = _extract_section(label, section_key)
            if not section_text:
                continue
            src = ChunkSource(
                source_id=f"{source_id}-{section_key}",
                source_organization=SOURCE_ORGANIZATION,
                source_name=source_name,
                source_year=source_year,
                recommendation_grade=None,
            )
            chunks = chunk_text(
                f"# {source_name} — {_section_label(section_key)}\n\n{section_text}",
                src,
                id_prefix=f"{source_id}-{section_key}-",
            )
            if chunks:
                embeddings = embedder.embed([c.text for c in chunks])
                for chunk, embedding in zip(chunks, embeddings):
                    corpus.upsert_chunk(chunk, embedding)
                total += len(chunks)

        logger.info("openFDA %s: processed", drug)
        # Polite rate limiting.
        time.sleep(0.1)

    return total


def _fetch_label(drug: str, api_key: str) -> dict | None:
    params: dict[str, Any] = {
        "search": f'openfda.generic_name:"{drug}"',
        "limit": "1",
    }
    if api_key:
        params["api_key"] = api_key
    try:
        resp = httpx.get(_OPENFDA_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return results[0] if results else None
    except Exception as exc:
        logger.warning("openFDA fetch failed for %s: %s", drug, exc)
        return None


def _extract_section(label: dict, key: str) -> str:
    val = label.get(key)
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    return str(val)


def _get_brand_generic(label: dict, fallback: str) -> str:
    openfda = label.get("openfda", {})
    brand = openfda.get("brand_name", [])
    generic = openfda.get("generic_name", [])
    parts = []
    if generic:
        parts.append(generic[0].title())
    if brand:
        parts.append(f"({brand[0].title()})")
    return " ".join(parts) if parts else fallback.title()


def _get_label_year(label: dict) -> int | None:
    effective = label.get("effective_time", "")
    if effective and len(effective) >= 4:
        try:
            return int(effective[:4])
        except ValueError:
            pass
    return None


def _section_label(key: str) -> str:
    return key.replace("_", " ").title()
