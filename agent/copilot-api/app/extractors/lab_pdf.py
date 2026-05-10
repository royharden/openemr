"""Lab PDF extractor — Workstream A (Plan §6).

Pipeline:
  1. In eval mode: return deterministic fixtures from _eval_mocks_a.
  2. In live mode:
     a. Render each PDF page to a base64 PNG via pypdfium2.
     b. Extract word-level bboxes from the text layer via pdfplumber.
     c. Call Anthropic Vision (claude-sonnet-4-6) to extract field dicts.
     d. For each field, find a verbatim bbox from the pdfplumber text layer
        (AgDR-0040: bbox is NOT VLM-emitted; it is derived deterministically).
        If bbox match fails, drop the claim entirely (lab PDFs require grounding).

Returns a dict shaped like ExtractedDocument (serialised to JSON by the route).
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import re
import string
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PAGES = 10
_MODEL = "claude-sonnet-4-6"
_BBOX_UNIT = "exact"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _words_match(window: list[str], quote_words: list[str]) -> bool:
    if len(window) != len(quote_words):
        return False
    _strip = str.maketrans("", "", string.punctuation)
    for w, q in zip(window, quote_words):
        if w.lower().translate(_strip) != q.lower().translate(_strip):
            return False
    return True


def _find_verbatim_bbox(
    quote: str | None,
    blocks: list[dict[str, Any]],
) -> tuple[float, float, float, float] | None:
    if not quote or not blocks:
        return None
    words = quote.split()
    if not words:
        return None
    n = len(words)
    for i in range(len(blocks) - n + 1):
        window = [b["text"] for b in blocks[i : i + n]]
        if _words_match(window, words):
            matched = blocks[i : i + n]
            x0 = min(b["x0"] for b in matched)
            y0 = min(b["y0"] for b in matched)
            x1 = max(b["x1"] for b in matched)
            y1 = max(b["y1"] for b in matched)
            return (
                round(min(max(x0, 0.0), 1.0), 6),
                round(min(max(y0, 0.0), 1.0), 6),
                round(min(max(x1, 0.0), 1.0), 6),
                round(min(max(y1, 0.0), 1.0), 6),
            )
    return None


def _get_page_count(pdf_bytes: bytes) -> int:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        doc = pdfium.PdfDocument(pdf_bytes)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return 1


def _page_to_base64_png(pdf_bytes: bytes, page_index: int) -> str:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        page = doc[page_index]
        bitmap = page.render(scale=2.0)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    finally:
        doc.close()


def _extract_text_blocks_pdfplumber(
    pdf_bytes: bytes, page_index: int, page_width: float, page_height: float
) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore[import-untyped]
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_index >= len(pdf.pages):
                return []
            page = pdf.pages[page_index]
            words = page.extract_words()
            blocks = []
            for w in words:
                if page_width > 0 and page_height > 0:
                    blocks.append({
                        "text": w["text"],
                        "x0": w["x0"] / page_width,
                        "y0": w["top"] / page_height,
                        "x1": w["x1"] / page_width,
                        "y1": w["bottom"] / page_height,
                    })
            return blocks
    except Exception as exc:
        logger.warning("pdfplumber failed on page %d: %s", page_index, exc)
        return []


def _get_page_dimensions(pdf_bytes: bytes, page_index: int) -> tuple[float, float]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        doc = pdfium.PdfDocument(pdf_bytes)
        try:
            page = doc[page_index]
            return float(page.get_width()), float(page.get_height())
        finally:
            doc.close()
    except Exception:
        return 612.0, 792.0


def _call_vision_api(image_b64: str, patient_uuid_hash: str) -> list[dict[str, Any]]:
    import anthropic  # type: ignore[import-untyped]
    client = anthropic.Anthropic()
    system = (
        "You are a clinical lab document parser. Extract structured lab results. "
        "Return a JSON array of objects, each with: name (snake_case field name), "
        "value (numeric or string), unit (string or null), abnormal (bool), "
        "quote_or_value (verbatim text from document, max 60 chars). "
        "Only include fields visible in the image. No hallucination."
    )
    response = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": "Extract all lab result fields from this page. Return JSON array only."},
                ],
            }
        ],
    )
    import json
    text = response.content[0].text.strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return []


def extract_lab_pdf(
    pdf_bytes: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "upload.pdf",
) -> dict[str, Any]:
    from app.extractors._eval_mocks_a import (
        get_lab_mock_fields,
        is_eval_mode,
        resolve_lab_fixture_key,
    )

    doc_sha = document_sha256 or _sha256_bytes(pdf_bytes)

    if is_eval_mode():
        from app.extractors._eval_mocks_a import MOCK_VERSION as _MV
        fixture_key = resolve_lab_fixture_key(doc_sha, filename)
        raw_fields = get_lab_mock_fields(fixture_key)
        fields = []
        for idx, f in enumerate(raw_fields):
            field_path = f"lab.{f['name']}"
            source_id = f"doc:{doc_sha[:12]}:page{f.get('page_index', 0)}:{f['name']}"
            fields.append({
                "name": f["name"],
                "value": f["value"],
                "unit": f.get("unit"),
                "abnormal": f.get("abnormal", False),
                "source_id": source_id,
                "quote_or_value": f.get("quote_or_value"),
                "page_index": f.get("page_index", 0),
                "bbox": None,
                "bbox_unit": None,
                "confidence": f.get("confidence", 0.95),
                "idempotency_key": hashlib.sha256(
                    f"{patient_uuid_hash}{doc_sha}{field_path}".encode()
                ).hexdigest(),
            })
        return {
            "doc_type": "lab_pdf",
            "document_sha256": doc_sha,
            "patient_uuid_hash": patient_uuid_hash,
            "filename": filename,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extracted_by": f"eval-mock/{_MV}",
            "extracted_field_count": len(fields),
            "result": {"fields": fields},
        }

    # Live mode
    page_count = _get_page_count(pdf_bytes)
    if page_count > _MAX_PAGES:
        raise ValueError(f"too_many_pages: {filename!r} has {page_count} pages; limit is {_MAX_PAGES}")

    all_fields: list[dict[str, Any]] = []
    for page_idx in range(page_count):
        try:
            image_b64 = _page_to_base64_png(pdf_bytes, page_idx)
            raw_fields = _call_vision_api(image_b64, patient_uuid_hash)
            width, height = _get_page_dimensions(pdf_bytes, page_idx)
            blocks = _extract_text_blocks_pdfplumber(pdf_bytes, page_idx, width, height)
            for f in raw_fields:
                name = f.get("name", "").strip()
                if not name:
                    continue
                quote = f.get("quote_or_value") or f.get("quote")
                bbox_tuple = _find_verbatim_bbox(quote, blocks)
                if bbox_tuple is None:
                    continue  # AgDR-0040: drop claim if no text-layer grounding
                field_path = f"lab.{name}"
                source_id = f"doc:{doc_sha[:12]}:page{page_idx}:{name}"
                all_fields.append({
                    "name": name,
                    "value": f.get("value"),
                    "unit": f.get("unit"),
                    "abnormal": bool(f.get("abnormal", False)),
                    "source_id": source_id,
                    "quote_or_value": quote,
                    "page_index": page_idx,
                    "bbox": list(bbox_tuple),
                    "bbox_unit": _BBOX_UNIT,
                    "confidence": float(f.get("confidence", 0.90)),
                    "idempotency_key": hashlib.sha256(
                        f"{patient_uuid_hash}{doc_sha}{field_path}".encode()
                    ).hexdigest(),
                })
        except Exception as exc:
            logger.error("Error processing page %d of %r: %s", page_idx, filename, exc)

    return {
        "doc_type": "lab_pdf",
        "document_sha256": doc_sha,
        "patient_uuid_hash": patient_uuid_hash,
        "filename": filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extracted_by": _MODEL,
        "extracted_field_count": len(all_fields),
        "result": {"fields": all_fields},
    }
