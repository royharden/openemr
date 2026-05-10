"""Lab PDF extractor — Anthropic Vision + pdfplumber bbox (Workstream A).

Pipeline per page:
  1. Render PDF page to base64 PNG via pypdfium2.
  2. Send image to Claude Vision with a structured extraction prompt.
  3. For each VLM-emitted field, search the pdfplumber text layer for a
     verbatim quote match and record the deterministic bbox (AgDR-0040).
  4. Drop any field whose quote_verbatim_in_pdf check fails.
  5. Return LabResult wrapped in ExtractedDocument.

COPILOT_EVAL_MODE=1 bypasses Anthropic and returns deterministic mock fields
so the eval gate never incurs API cost.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PAGES = 10
_MAX_BYTES = 8 * 1024 * 1024  # 8 MB

_VISION_MODEL = os.environ.get("COPILOT_VISION_MODEL", "claude-sonnet-4-6")

_LAB_EXTRACT_PROMPT = """You are a clinical lab report parser. Extract ALL lab results from this page.

Return ONLY a JSON array (no markdown). Each element:
{
  "name": "field_path (e.g. ldl, cholesterol_total, wbc)",
  "value": <number or string>,
  "unit": "<unit string or null>",
  "flag": "<H|L|N|A|null>",
  "reference_range": "<range string or null>",
  "loinc_code": "<LOINC code or null>",
  "verbatim_quote": "<exact text from the document containing this value, or null if not text layer>"
}

Rules:
- Use snake_case field names.
- Prefer numeric values for numeric results.
- verbatim_quote must be text that appears word-for-word in the PDF text layer.
- Do NOT invent values. If uncertain, omit the field entirely.
- Return [] if no lab results are visible on this page."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _page_to_base64_png(pdf_bytes: bytes, page_index: int) -> str:
    """Render one PDF page to a base64-encoded PNG using pypdfium2."""
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        page = doc[page_index]
        bitmap = page.render(scale=2.0)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode()
    finally:
        doc.close()


def _get_page_count(pdf_bytes: bytes) -> int:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(doc)
    finally:
        doc.close()


def _extract_text_blocks_pdfplumber(pdf_bytes: bytes, page_index: int) -> list[dict[str, Any]]:
    """Return word-level blocks from pdfplumber for bbox lookup.

    Each block: {"text": str, "x0": float, "y0": float, "x1": float, "y1": float,
                  "page_width": float, "page_height": float}
    """
    import pdfplumber  # type: ignore[import-untyped]

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if page_index >= len(pdf.pages):
            return []
        page = pdf.pages[page_index]
        words = page.extract_words()
        pw, ph = float(page.width), float(page.height)
        blocks = []
        for w in words:
            blocks.append({
                "text": w["text"],
                "x0": float(w["x0"]),
                "y0": float(w["top"]),
                "x1": float(w["x1"]),
                "y1": float(w["bottom"]),
                "page_width": pw,
                "page_height": ph,
            })
        return blocks


def _find_verbatim_bbox(
    quote: str,
    blocks: list[dict[str, Any]],
) -> tuple[float, float, float, float] | None:
    """Find the bounding box of a verbatim quote in pdfplumber word blocks.

    Scans the text layer for a sequence of words that matches the normalized
    quote. Returns normalized (x0, y0, x1, y1) in [0,1] or None if not found.

    Per AgDR-0040: bbox is always derived from pdfplumber text layer, never
    from VLM coordinates.
    """
    if not quote or not blocks:
        return None

    quote_words = re.split(r"\s+", quote.strip())
    quote_words = [w for w in quote_words if w]
    if not quote_words:
        return None

    block_texts = [b["text"] for b in blocks]
    n = len(quote_words)

    for start in range(len(blocks) - n + 1):
        window = block_texts[start:start + n]
        if _words_match(window, quote_words):
            matched = blocks[start:start + n]
            pw = matched[0]["page_width"]
            ph = matched[0]["page_height"]
            if pw <= 0 or ph <= 0:
                return None
            x0 = min(b["x0"] for b in matched) / pw
            y0 = min(b["y0"] for b in matched) / ph
            x1 = max(b["x1"] for b in matched) / pw
            y1 = max(b["y1"] for b in matched) / ph
            # Clamp to [0, 1]
            x0, y0, x1, y1 = (
                max(0.0, min(1.0, x0)),
                max(0.0, min(1.0, y0)),
                max(0.0, min(1.0, x1)),
                max(0.0, min(1.0, y1)),
            )
            if x0 < x1 and y0 < y1:
                return (x0, y0, x1, y1)

    return None


def _words_match(window: list[str], quote_words: list[str]) -> bool:
    """Case-insensitive, punctuation-tolerant word match."""
    if len(window) != len(quote_words):
        return False
    for w, q in zip(window, quote_words):
        if w.lower().rstrip(".,;:") != q.lower().rstrip(".,;:"):
            return False
    return True


def _call_vision_api(image_b64: str, patient_uuid_hash: str) -> list[dict[str, Any]]:
    """Call Anthropic Vision API and return parsed field list."""
    import anthropic  # type: ignore[import-untyped]

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=_VISION_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": _LAB_EXTRACT_PROMPT},
                ],
            }
        ],
    )

    raw = message.content[0].text if message.content else "[]"
    # Strip markdown fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Lab PDF vision response was not valid JSON; returning empty list")
        return []


def extract_lab_pdf(
    pdf_bytes: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "",
) -> dict[str, Any]:
    """Extract structured lab results from a PDF.

    Returns a dict matching ExtractedDocument shape.
    Caller (route handler) is responsible for Pydantic coercion.

    Args:
        pdf_bytes: Raw PDF content (already validated <=10 pages, <=8MB by controller).
        patient_uuid_hash: SHA-256 of patient UUID (for citation SourcePacket).
        document_sha256: Pre-computed SHA-256 hex; computed here if not provided.
        filename: Original filename hint (used in eval mode for fixture lookup).
    """
    from ..schemas import ExtractedDocument, ExtractedField, LabResult, SourcePacket
    from ._eval_mocks_a import (
        get_lab_mock_fields,
        is_eval_mode,
        resolve_lab_fixture_key,
    )

    if document_sha256 is None:
        document_sha256 = _sha256_bytes(pdf_bytes)

    eval_mode = is_eval_mode()

    if eval_mode:
        fixture_key = resolve_lab_fixture_key(document_sha256, filename)
        mock_fields = get_lab_mock_fields(fixture_key)
        page_count = 1
        extracted_fields = _build_fields_from_mocks_lab(
            mock_fields, document_sha256, patient_uuid_hash
        )
    else:
        page_count = _get_page_count(pdf_bytes)
        if page_count > _MAX_PAGES:
            raise ValueError(f"PDF has {page_count} pages; maximum is {_MAX_PAGES}")

        extracted_fields = _extract_all_pages_lab(
            pdf_bytes, page_count, document_sha256, patient_uuid_hash
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    model_used = "eval-mock" if eval_mode else _VISION_MODEL

    lab_result = LabResult(
        document_sha256=document_sha256,
        page_count=page_count,
        extracted_at=now_iso,
        extracted_by_model=model_used,
        fields=extracted_fields,
    )

    dropped = sum(1 for f in extracted_fields if f.citation is None and f.value is not None)

    return ExtractedDocument(
        doc_type="lab_pdf",
        document_sha256=document_sha256,
        result=lab_result,
        source_packets=[f.citation for f in extracted_fields if f.citation is not None],
        extracted_field_count=len(extracted_fields),
        dropped_field_count=dropped,
    ).model_dump(mode="json")


def _extract_all_pages_lab(
    pdf_bytes: bytes,
    page_count: int,
    document_sha256: str,
    patient_uuid_hash: str,
) -> list[Any]:
    from ..schemas import ExtractedField, SourcePacket

    all_fields = []
    for page_idx in range(page_count):
        try:
            image_b64 = _page_to_base64_png(pdf_bytes, page_idx)
            raw_fields = _call_vision_api(image_b64, patient_uuid_hash)
            blocks = _extract_text_blocks_pdfplumber(pdf_bytes, page_idx)
        except Exception as exc:
            logger.error("Failed to extract page %d: %s", page_idx, exc)
            continue

        for raw in raw_fields:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                continue

            value = raw.get("value")
            unit = raw.get("unit") or None
            flag = raw.get("flag") or None
            ref = raw.get("reference_range") or None
            loinc = raw.get("loinc_code") or None
            quote = raw.get("verbatim_quote") or None

            bbox: tuple[float, float, float, float] | None = None
            if quote:
                bbox = _find_verbatim_bbox(quote, blocks)
                if bbox is None:
                    # Per AgDR-0040: drop the claim if verbatim match fails
                    logger.debug("Verbatim match failed for field %r; dropping citation", name)
                    quote = None

            citation: Any = None
            if quote is not None or bbox is not None:
                citation = SourcePacket(
                    source_id=f"doc:{document_sha256[:12]}:page{page_idx}:{name}",
                    patient_uuid=patient_uuid_hash,
                    resource_type="DocumentFact",
                    source_table="copilot_document_facts",
                    field=name,
                    label=name.replace("_", " ").title(),
                    value=value,
                    unit=unit,
                    source_type="document_extract",
                    page_or_section=f"page:{page_idx}",
                    field_or_chunk_id=name,
                    quote_or_value=quote,
                    bbox=bbox,
                    bbox_unit="exact" if bbox is not None else None,
                    confidence=0.95 if bbox is not None else 0.70,
                    page_index=page_idx,
                )

            all_fields.append(
                ExtractedField(
                    name=name,
                    value=value,
                    unit=unit,
                    reference_range=ref,
                    flag=flag,
                    loinc_code=loinc,
                    citation=citation,
                )
            )

    return all_fields


def _build_fields_from_mocks_lab(
    mock_fields: list[Any],
    document_sha256: str,
    patient_uuid_hash: str,
) -> list[Any]:
    from ..schemas import ExtractedField, SourcePacket

    fields = []
    for row in mock_fields:
        name, value, unit, flag, ref, loinc, page_idx, bbox, quote = row
        citation = SourcePacket(
            source_id=f"doc:{document_sha256[:12]}:page{page_idx}:{name}",
            patient_uuid=patient_uuid_hash,
            resource_type="DocumentFact",
            source_table="copilot_document_facts",
            field=name,
            label=name.replace("_", " ").title(),
            value=value,
            unit=unit,
            source_type="document_extract",
            page_or_section=f"page:{page_idx}",
            field_or_chunk_id=name,
            quote_or_value=quote,
            bbox=bbox,
            bbox_unit="exact" if bbox is not None else None,
            confidence=0.95 if bbox is not None else 0.70,
            page_index=page_idx,
        )
        fields.append(
            ExtractedField(
                name=name,
                value=value,
                unit=unit,
                reference_range=ref,
                flag=flag,
                loinc_code=loinc,
                citation=citation,
            )
        )
    return fields
