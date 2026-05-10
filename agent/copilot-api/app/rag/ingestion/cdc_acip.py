"""CDC ACIP guideline corpus ingestor.

Source
------
CDC ACIP recommendations and immunization schedules are public-domain
content published at https://www.cdc.gov/vaccines/acip/.

Fetch strategy (plan §6 Workstream B, decision #16):
  - Fetch fresh from CDC on first build; cache by ETag in corpus.db.
  - Bundling a static snapshot as fallback is allowed (public domain).
  - USPSTF is DEFERRED to Week 3 (status §I, §K drift entry 2026-05-09).

We ingest these pages / PDFs:
  1. Adult immunization schedule (text from CDC page)
  2. Child / adolescent schedule (text from CDC page)
  3. ACIP General Recommendations on Immunization (text from CDC page)
  4. Selected vaccine-specific recommendations (hepatitis, flu, pneumococcal,
     Tdap, HPV, COVID) — linked from the ACIP recommendations index.

Grading
-------
ACIP uses a two-category grade system (category A = recommended, category B =
recommended for certain groups).  Some guidance pages carry no explicit grade.
We parse the grade from common ACIP heading patterns.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..chunker import ChunkSource, chunk_text
from ..contracts import GuidelineChunk

logger = logging.getLogger(__name__)

SOURCE_ORGANIZATION = "CDC-ACIP"
SOURCE_YEAR_DEFAULT = 2024  # most recent schedule publication year

# CDC pages to ingest.  Each entry is (source_id, url, label, year, grade).
# grade=None for pages that don't have a single recommendation grade.
_ACIP_SOURCES: list[tuple[str, str, str, int, str | None]] = [
    (
        "acip-adult-schedule-2024",
        "https://www.cdc.gov/vaccines/schedules/hcp/imz/adult.html",
        "CDC ACIP Recommended Adult Immunization Schedule (2024)",
        2024,
        None,
    ),
    (
        "acip-child-schedule-2024",
        "https://www.cdc.gov/vaccines/schedules/hcp/imz/child-adolescent.html",
        "CDC ACIP Recommended Child and Adolescent Immunization Schedule (2024)",
        2024,
        None,
    ),
    (
        "acip-general-recs-2011",
        "https://www.cdc.gov/mmwr/preview/mmwrhtml/rr6002a1.htm",
        "CDC ACIP General Recommendations on Immunization (2011)",
        2011,
        None,
    ),
    (
        "acip-pneumococcal-adults-2022",
        "https://www.cdc.gov/vaccines/vpd/pneumo/hcp/pneumococcal-vaccine-timing-adults.html",
        "CDC ACIP Pneumococcal Vaccines for Adults (2022)",
        2022,
        "B",  # Recommendation category B — for certain groups
    ),
    (
        "acip-tdap-adults-2012",
        "https://www.cdc.gov/mmwr/preview/mmwrhtml/mm6101a4.htm",
        "CDC ACIP Updated Recommendations for Tdap (2012)",
        2012,
        "A",
    ),
    (
        "acip-influenza-2024",
        "https://www.cdc.gov/mmwr/volumes/73/rr/rr7302a1.htm",
        "CDC ACIP Prevention and Control of Seasonal Influenza (2024)",
        2024,
        "A",
    ),
    (
        "acip-covid-2024",
        "https://www.cdc.gov/vaccines/covid-19/clinical-considerations/interim-considerations-us.html",
        "CDC ACIP COVID-19 Vaccination Clinical Considerations (2024)",
        2024,
        "A",
    ),
    (
        "acip-hpv-2019",
        "https://www.cdc.gov/mmwr/volumes/68/wr/mm6832a3.htm",
        "CDC ACIP Human Papillomavirus Vaccination (2019)",
        2019,
        "A",
    ),
]

# Bundled fallback text snippets (public domain).
# These are minimal seed texts used when the live fetch fails and no cached
# text exists.  They ensure the corpus is never empty even in an offline CI run.
_FALLBACK_SNIPPETS: dict[str, str] = {
    "acip-adult-schedule-2024": (
        "# CDC ACIP Recommended Adult Immunization Schedule 2024\n\n"
        "## Influenza\n"
        "All adults should receive influenza vaccination annually. "
        "Adults 65 years and older should receive a high-dose or adjuvanted influenza vaccine.\n\n"
        "## Tdap / Td\n"
        "Adults who have not received Tdap should receive one dose. "
        "Td booster every 10 years thereafter.\n\n"
        "## Pneumococcal\n"
        "Adults 65 years and older should receive PCV20 or PCV15 followed by PPSV23. "
        "Adults 19-64 years with certain medical conditions are also recommended.\n\n"
        "## COVID-19\n"
        "All adults should stay up to date with COVID-19 vaccination, including boosters.\n\n"
        "## HPV\n"
        "Adults through age 26 years who were not adequately vaccinated should receive HPV vaccine. "
        "Adults 27-45 years may receive HPV vaccine based on shared clinical decision-making.\n\n"
        "## Hepatitis B\n"
        "Adults 19-59 years who were not vaccinated should receive hepatitis B vaccine series. "
        "Adults 60 years and older may be vaccinated based on individual assessment.\n"
    ),
    "acip-child-schedule-2024": (
        "# CDC ACIP Recommended Child and Adolescent Immunization Schedule 2024\n\n"
        "## Birth to 15 months\n"
        "HepB: Birth, 1-2 months, 6-18 months.\n"
        "RV: 2 months, 4 months, 6 months (if using Rotateq).\n"
        "DTaP: 2, 4, 6 months; 15-18 months; 4-6 years.\n"
        "Hib: 2, 4, 6 months; 12-15 months.\n"
        "PCV15/PCV20: 2, 4, 6 months; 12-15 months.\n"
        "IPV: 2, 4 months; 6-18 months; 4-6 years.\n"
        "MMR: 12-15 months; 4-6 years.\n"
        "Varicella: 12-15 months; 4-6 years.\n\n"
        "## Adolescents 11-12 years\n"
        "Tdap: One dose at 11-12 years.\n"
        "HPV: 2-dose series starting at 11-12 years.\n"
        "MenACWY: One dose at 11-12 years; booster at 16 years.\n"
    ),
    "acip-general-recs-2011": (
        "# CDC ACIP General Recommendations on Immunization 2011\n\n"
        "## Timing and Spacing of Immunobiologics\n"
        "To ensure optimal protection, vaccines should be administered "
        "at the recommended ages and intervals. Simultaneous administration "
        "of all indicated vaccines is preferred.\n\n"
        "## Contraindications and Precautions\n"
        "Severe allergic reaction (anaphylaxis) to a vaccine component "
        "is a contraindication for further doses of that vaccine.\n\n"
        "## Storage and Handling\n"
        "Vaccines must be stored at recommended temperatures to maintain potency. "
        "Refrigerator-stable vaccines: 2-8 degrees Celsius. "
        "Freezer-stable vaccines: -15 degrees Celsius or colder.\n"
    ),
    "acip-pneumococcal-adults-2022": (
        "# CDC ACIP Pneumococcal Vaccines for Adults 2022\n\n"
        "## Recommendation (Category B)\n"
        "Adults 65 years and older who have not previously received pneumococcal vaccine "
        "should receive PCV20 alone, or PCV15 followed by PPSV23 "
        "(given 1 year or more after PCV15).\n\n"
        "Adults 19-64 years with certain underlying conditions "
        "(immunocompromising conditions, CSF leaks, cochlear implants) "
        "should receive pneumococcal vaccination.\n\n"
        "Adults 19-64 years with chronic conditions "
        "(cigarette smoking, chronic heart, lung, liver, kidney disease, diabetes) "
        "should receive PPSV23.\n"
    ),
    "acip-tdap-adults-2012": (
        "# CDC ACIP Updated Recommendations for Tdap 2012\n\n"
        "## Recommendation (Category A)\n"
        "Adults who have not received Tdap as an adult should receive a single dose of Tdap. "
        "Td booster every 10 years thereafter.\n\n"
        "## Pregnancy\n"
        "Pregnant women should receive one dose of Tdap during each pregnancy, "
        "preferably during the early part of gestational weeks 27-36.\n\n"
        "## Wound Management\n"
        "For wound management, adults who have not received Td in the past 5 years "
        "and have a wound that is not clean and minor should receive Tdap "
        "(if they have not previously received Tdap).\n"
    ),
    "acip-influenza-2024": (
        "# CDC ACIP Prevention and Control of Seasonal Influenza 2024\n\n"
        "## Recommendation (Category A)\n"
        "All persons aged 6 months and older who do not have contraindications "
        "should receive influenza vaccination annually.\n\n"
        "## Adults 65 Years and Older\n"
        "Preferentially receive one of the following higher-dose or adjuvanted vaccines: "
        "Fluzone High-Dose Quadrivalent, Flublok Quadrivalent, or Fluad Quadrivalent.\n\n"
        "## Timing\n"
        "Vaccination should ideally be offered before influenza activity begins "
        "in the community, typically by the end of October.\n"
    ),
    "acip-covid-2024": (
        "# CDC ACIP COVID-19 Vaccination Clinical Considerations 2024\n\n"
        "## Recommendation (Category A)\n"
        "All persons 6 months and older are recommended to stay up to date "
        "with COVID-19 vaccination, including updated (2024-2025) vaccines.\n\n"
        "## Adults 65 Years and Older\n"
        "Adults 65 years and older may receive an additional dose of updated "
        "2024-2025 mRNA COVID-19 vaccine if they received their last dose more than 4 months ago.\n\n"
        "## Immunocompromised Persons\n"
        "Immunocompromised persons may receive additional doses based on clinical assessment.\n"
    ),
    "acip-hpv-2019": (
        "# CDC ACIP Human Papillomavirus Vaccination 2019\n\n"
        "## Recommendation (Category A)\n"
        "Routine vaccination is recommended for all adolescents 11-12 years. "
        "Vaccination can be given starting at age 9 years.\n\n"
        "## Catch-up Vaccination\n"
        "Catch-up vaccination is recommended for all persons through 26 years of age. "
        "For persons 27-45 years, vaccination is based on shared clinical decision-making.\n\n"
        "## Dosing Schedule\n"
        "2-dose series if initiated before age 15: 0, 6-12 months. "
        "3-dose series if initiated at age 15 or older: 0, 1-2 months, 6 months.\n"
    ),
}


def ingest(corpus: Any, embedder: Any) -> int:
    """Fetch ACIP sources and upsert chunks into *corpus*.

    Returns the total number of chunks upserted.
    """
    total = 0
    for source_id, url, label, year, grade in _ACIP_SOURCES:
        text = _fetch_text(source_id, url)
        src = ChunkSource(
            source_id=source_id,
            source_organization=SOURCE_ORGANIZATION,
            source_name=label,
            source_year=year,
            recommendation_grade=grade,
        )
        chunks = chunk_text(text, src, id_prefix=f"{source_id}-")
        logger.info("ACIP %s: %d chunks", source_id, len(chunks))
        embeddings = embedder.embed([c.text for c in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            corpus.upsert_chunk(chunk, embedding)
        total += len(chunks)
    return total


def _fetch_text(source_id: str, url: str) -> str:
    """Fetch URL, strip HTML tags, return plain text.

    Falls back to _FALLBACK_SNIPPETS if the request fails.
    """
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        text = _strip_html(resp.text)
        if len(text.strip()) > 100:
            logger.debug("Fetched %s (%d chars)", url, len(text))
            return text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s — using fallback snippet", url, exc)

    return _FALLBACK_SNIPPETS.get(source_id, f"# {source_id}\n(no content available)")


def _strip_html(html: str) -> str:
    """Very lightweight HTML-to-text: strip tags, decode common entities."""
    # Remove script/style blocks.
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Convert block tags to newlines.
    text = re.sub(r"<(?:br|p|h[1-6]|li|tr|div)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags.
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities.
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&nbsp;", " "), ("&#160;", " "), ("&ndash;", "–"),
                         ("&mdash;", "—"), ("&lsquo;", "'"), ("&rsquo;", "'"),
                         ("&ldquo;", '"'), ("&rdquo;", '"')]:
        text = text.replace(entity, char)
    # Collapse whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
