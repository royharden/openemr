"""Intake form extractor — Anthropic Vision + pdfplumber bbox (Workstream A).

Handles both typed PDFs and scanned/handwritten image forms (PNG/JPEG).
For typed PDFs, pdfplumber provides a text layer for verbatim matching.
For image-only inputs (PNG/JPEG or text-free PDFs), bbox is skipped and
confidence is lower.

COPILOT_EVAL_MODE=1 bypasses Anthropic and returns deterministic mocks.
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
_MAX_BYTES = 8 * 1024 * 1024

_VISION_MODEL = os.environ.get("COPILOT_VISION_MODEL", "claude-sonnet-4-6")

_INTAKE_EXTRACT_PROMPT = """You are a medical intake form parser. Extract ALL structured fields from this form.

Return ONLY a JSON array (no markdown). Each element:
{
  "name": "field_path using snake_case dot notation (e.g. vitals.bp_systolic, chief_complaint, allergies.self_reported)",
  "value": <string or number>,
  "verbatim_quote": "<exact text from the form containing this value, or null if handwritten/image-only>"
}

Rules:
- Use descriptive snake_case paths: vitals.height, vitals.weight, vitals.bp_systolic, vitals.bp_diastolic,
  chief_complaint, smoking_status, alcohol_use, medications.self_reported, allergies.self_reported,
  family_history, symptoms, review_of_systems.
- verbatim_quote must be text that appears word-for-word in a typed/printed form.
  For handwritten text, set verbatim_quote to null.
- Do NOT invent values. If a field is blank, omit it.
- Return [] if no structured fields are visible."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _detect_media_type(content: bytes, filename: str = "") -> str:
    """Detect media type from magic bytes or filename."""
    if content[:4] == b"%PDF":
        return "application/pdf"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    fn = filename.lower()
    if fn.endswith(".pdf"):
        return "application/pdf"
    if fn.endswith(".png"):
        return "image/png"
    if fn.endswith(".jpg") or fn.endswith(".jpeg"):
        return "image/jpeg"
    return "application/pdf"


def _get_page_count_pdf(pdf_bytes: bytes) -> int:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(doc)
    finally:
        doc.close()


def _pdf_page_to_base64_png(pdf_bytes: bytes, page_index: int) -> str:
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


def _image_to_base64(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode()


def _extract_text_blocks_pdfplumber(pdf_bytes: bytes, page_index: int) -> list[dict[str, Any]]:
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
    """Verbatim bbox search — same algorithm as lab_pdf for consistency."""
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
            x0 = max(0.0, min(1.0, min(b["x0"] for b in matched) / pw))
            y0 = max(0.0, min(1.0, min(b["y0"] for b in matched) / ph))
            x1 = max(0.0, min(1.0, max(b["x1"] for b in matched) / pw))
            y1 = max(0.0, min(1.0, max(b["y1"] for b in matched) / ph))
            if x0 < x1 and y0 < y1:
                return (x0, y0, x1, y1)
    return None


def _words_match(window: list[str], quote_words: list[str]) -> bool:
    if len(window) != len(quote_words):
        return False
    for w, q in zip(window, quote_words):
        if w.lower().rstrip(".,;:") != q.lower().rstrip(".,;:"):
            return False
    return True


def _call_vision_api(image_b64: str, media_type: str) -> list[dict[str, Any]]:
    import anthropic  # type: ignore[import-untyped]

    mt = media_type if media_type in ("image/png", "image/jpeg", "image/gif", "image/webp") else "image/png"
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
                            "media_type": mt,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": _INTAKE_EXTRACT_PROMPT},
                ],
            }
        ],
    )
    raw = message.content[0].text if message.content else "[]"
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Intake form vision response was not valid JSON; returning empty list")
        return []


def extract_intake_form(
    content: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "",
) -> dict[str, Any]:
    """Extract structured fields from an intake form (PDF, PNG, or JPEG).

    Args:
        content: Raw file bytes (already validated <=10 pages, <=8MB).
        patient_uuid_hash: SHA-256 of patient UUID.
        document_sha256: Pre-computed SHA-256 hex; computed if not provided.
        filename: Original filename hint.
    """
    from ..schemas import ExtractedDocument, ExtractedField, IntakeFields, SourcePacket
    from ._eval_mocks_a import (
        get_intake_mock_fields,
        is_eval_mode,
        resolve_intake_fixture_key,
    )

    if document_sha256 is None:
        document_sha256 = _sha256_bytes(content)

    eval_mode = is_eval_mode()
    media_type = _detect_media_type(content, filename)
    is_pdf = media_type == "application/pdf"

    if eval_mode:
        fixture_key = resolve_intake_fixture_key(document_sha256, filename)
        mock_fields = get_intake_mock_fields(fixture_key)
        page_count = 1
        extracted_fields = _build_fields_from_mocks_intake(
            mock_fields, document_sha256, patient_uuid_hash
        )
    else:
        if is_pdf:
            page_count = _get_page_count_pdf(content)
            if page_count > _MAX_PAGES:
                raise ValueError(f"PDF has {page_count} pages; maximum is {_MAX_PAGES}")
            extracted_fields = _extract_pdf_pages_intake(
                content, page_count, document_sha256, patient_uuid_hash
            )
        else:
            page_count = 1
            extracted_fields = _extract_image_intake(
                content, media_type, document_sha256, patient_uuid_hash
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    model_used = "eval-mock" if eval_mode else _VISION_MODEL

    intake = IntakeFields(
        document_sha256=document_sha256,
        page_count=page_count,
        extracted_at=now_iso,
        extracted_by_model=model_used,
        fields=extracted_fields,
    )

    dropped = sum(1 for f in extracted_fields if f.citation is None and f.value is not None)

    return ExtractedDocument(
        doc_type="intake_form",
        document_sha256=document_sha256,
        result=intake,
        source_packets=[f.citation for f in extracted_fields if f.citation is not None],
        extracted_field_count=len(extracted_fields),
        dropped_field_count=dropped,
    ).model_dump(mode="json")


def _extract_pdf_pages_intake(
    pdf_bytes: bytes,
    page_count: int,
    document_sha256: str,
    patient_uuid_hash: str,
) -> list[Any]:
    from ..schemas import ExtractedField, SourcePacket

    all_fields = []
    for page_idx in range(page_count):
        try:
            image_b64 = _pdf_page_to_base64_png(pdf_bytes, page_idx)
            raw_fields = _call_vision_api(image_b64, "image/png")
            blocks = _extract_text_blocks_pdfplumber(pdf_bytes, page_idx)
        except Exception as exc:
            logger.error("Failed to extract intake page %d: %s", page_idx, exc)
            continue

        for raw in raw_fields:
            field = _process_raw_intake_field(
                raw, page_idx, blocks, document_sha256, patient_uuid_hash
            )
            if field is not None:
                all_fields.append(field)

    return all_fields


def _extract_image_intake(
    image_bytes: bytes,
    media_type: str,
    document_sha256: str,
    patient_uuid_hash: str,
) -> list[Any]:
    from ..schemas import ExtractedField, SourcePacket

    try:
        image_b64 = _image_to_base64(image_bytes)
        raw_fields = _call_vision_api(image_b64, media_type)
    except Exception as exc:
        logger.error("Failed to extract intake image: %s", exc)
        return []

    fields = []
    for raw in raw_fields:
        # No text layer for images — skip bbox lookup
        field = _process_raw_intake_field(
            raw, 0, [], document_sha256, patient_uuid_hash
        )
        if field is not None:
            fields.append(field)
    return fields


def _process_raw_intake_field(
    raw: Any,
    page_idx: int,
    blocks: list[dict[str, Any]],
    document_sha256: str,
    patient_uuid_hash: str,
) -> Any:
    from ..schemas import ExtractedField, SourcePacket

    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None

    value = raw.get("value")
    quote = raw.get("verbatim_quote") or None

    bbox: tuple[float, float, float, float] | None = None
    if quote and blocks:
        bbox = _find_verbatim_bbox(quote, blocks)
        if bbox is None:
            # For intake forms with handwritten fields, a null bbox is acceptable
            # (image-only; not a reason to drop the field)
            logger.debug("Verbatim match failed for intake field %r; keeping without bbox", name)

    has_citation = quote is not None or bbox is not None
    citation = None
    if has_citation or value is not None:
        citation = SourcePacket(
            source_id=f"doc:{document_sha256[:12]}:page{page_idx}:{name}",
            patient_uuid=patient_uuid_hash,
            resource_type="DocumentFact",
            source_table="copilot_document_facts",
            field=name,
            label=name.replace("_", " ").replace(".", " ").title(),
            value=value,
            source_type="document_extract",
            page_or_section=f"page:{page_idx}",
            field_or_chunk_id=name,
            quote_or_value=quote,
            bbox=bbox,
            bbox_unit="exact" if bbox is not None else None,
            confidence=0.90 if bbox is not None else (0.70 if quote else 0.60),
            page_index=page_idx,
        )

    return ExtractedField(
        name=name,
        value=value,
        citation=citation,
    )


def _build_fields_from_mocks_intake(
    mock_fields: list[Any],
    document_sha256: str,
    patient_uuid_hash: str,
) -> list[Any]:
    from ..schemas import ExtractedField, SourcePacket

    fields = []
    for row in mock_fields:
        name, value, page_idx, quote = row
        citation = SourcePacket(
            source_id=f"doc:{document_sha256[:12]}:page{page_idx}:{name}",
            patient_uuid=patient_uuid_hash,
            resource_type="DocumentFact",
            source_table="copilot_document_facts",
            field=name,
            label=name.replace("_", " ").replace(".", " ").title(),
            value=value,
            source_type="document_extract",
            page_or_section=f"page:{page_idx}",
            field_or_chunk_id=name,
            quote_or_value=quote,
            bbox=None,
            bbox_unit=None,
            confidence=0.85 if quote else 0.65,
            page_index=page_idx,
        )
        fields.append(
            ExtractedField(
                name=name,
                value=value,
                citation=citation,
            )
        )
    return fields
