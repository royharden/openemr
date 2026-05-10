"""Intake form extractor — Workstream A (Plan §6).

Handles PDF, PNG, and JPEG intake forms.

Key differences from lab_pdf:
  - Image-only forms: bbox is allowed to be null (handwritten PNG/JPEG have no
    text layer — the citation is still valid with null bbox, per AgDR-0040).
  - Lab PDFs drop the claim if no bbox; intake forms keep the field.
  - Media type is detected from magic bytes first, then extension fallback.
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

_MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}


def _detect_media_type(content: bytes, filename: str) -> str:
    for magic, mime in _MAGIC_BYTES.items():
        if content[: len(magic)] == magic:
            return mime
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "application/pdf")


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


def _pdf_page_to_base64_png(pdf_bytes: bytes, page_index: int) -> str:
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


def _image_to_base64_png(content: bytes, media_type: str) -> tuple[str, str]:
    if media_type == "image/png":
        return base64.b64encode(content).decode(), "image/png"
    if media_type == "image/jpeg":
        return base64.b64encode(content).decode(), "image/jpeg"
    return base64.b64encode(content).decode(), "image/png"


def _extract_text_blocks_pdfplumber(
    pdf_bytes: bytes, page_index: int
) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore[import-untyped]
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_index >= len(pdf.pages):
                return []
            page = pdf.pages[page_index]
            width = float(page.width) if page.width else 612.0
            height = float(page.height) if page.height else 792.0
            words = page.extract_words()
            blocks = []
            for w in words:
                if width > 0 and height > 0:
                    blocks.append({
                        "text": w["text"],
                        "x0": w["x0"] / width,
                        "y0": w["top"] / height,
                        "x1": w["x1"] / width,
                        "y1": w["bottom"] / height,
                    })
            return blocks
    except Exception as exc:
        logger.warning("pdfplumber failed on page %d: %s", page_index, exc)
        return []


def _call_vision_api_intake(
    image_b64: str, media_type: str, patient_uuid_hash: str
) -> list[dict[str, Any]]:
    import anthropic  # type: ignore[import-untyped]
    client = anthropic.Anthropic()
    system = (
        "You are a clinical intake form parser. Extract structured patient intake data. "
        "Return a JSON array of objects, each with: name (dot-notated field path e.g. "
        "'vitals.blood_pressure', 'chief_complaint', 'medications.self_reported'), "
        "value (string or number), quote_or_value (verbatim text from form if typed, "
        "null if handwritten and illegible). "
        "Only include fields actually present in the image."
    )
    import anthropic as _anthropic
    response = _anthropic.Anthropic().messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": "Extract all intake form fields. Return JSON array only."},
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


def _process_raw_intake_field(
    raw: dict[str, Any],
    page_idx: int,
    blocks: list[dict[str, Any]],
    doc_sha: str,
    patient_uuid_hash: str,
) -> dict[str, Any] | None:
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    value = raw.get("value")
    quote = raw.get("quote_or_value")
    bbox_tuple = _find_verbatim_bbox(quote, blocks) if quote else None
    field_path = f"intake.{name}"
    source_id = f"doc:{doc_sha[:12]}:page{page_idx}:{name}"
    return {
        "name": name,
        "value": value,
        "unit": raw.get("unit"),
        "abnormal": bool(raw.get("abnormal", False)),
        "source_id": source_id,
        "quote_or_value": quote,
        "page_index": page_idx,
        "bbox": list(bbox_tuple) if bbox_tuple else None,
        "bbox_unit": _BBOX_UNIT if bbox_tuple else None,
        "confidence": float(raw.get("confidence", 0.85)),
        "idempotency_key": hashlib.sha256(
            f"{patient_uuid_hash}{doc_sha}{field_path}".encode()
        ).hexdigest(),
    }


def extract_intake_form(
    content: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "upload.pdf",
) -> dict[str, Any]:
    from app.extractors._eval_mocks_a import (
        get_intake_mock_fields,
        is_eval_mode,
        resolve_intake_fixture_key,
        MOCK_VERSION,
    )

    doc_sha = document_sha256 or _sha256_bytes(content)

    if is_eval_mode():
        fixture_key = resolve_intake_fixture_key(doc_sha, filename)
        raw_fields = get_intake_mock_fields(fixture_key)
        fields = []
        for f in raw_fields:
            field_path = f"intake.{f['name']}"
            source_id = f"doc:{doc_sha[:12]}:page{f.get('page_index', 0)}:{f['name']}"
            fields.append({
                "name": f["name"],
                "value": f["value"],
                "unit": f.get("unit"),
                "abnormal": f.get("abnormal", False),
                "source_id": source_id,
                "quote_or_value": f.get("quote_or_value"),
                "page_index": f.get("page_index", 0),
                "bbox": f.get("bbox"),
                "bbox_unit": _BBOX_UNIT if f.get("bbox") else None,
                "confidence": f.get("confidence", 0.85),
                "idempotency_key": hashlib.sha256(
                    f"{patient_uuid_hash}{doc_sha}{field_path}".encode()
                ).hexdigest(),
            })
        return {
            "doc_type": "intake_form",
            "document_sha256": doc_sha,
            "patient_uuid_hash": patient_uuid_hash,
            "filename": filename,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extracted_by": f"eval-mock/{MOCK_VERSION}",
            "extracted_field_count": len(fields),
            "result": {"fields": fields},
        }

    # Live mode
    media_type = _detect_media_type(content, filename)
    all_fields: list[dict[str, Any]] = []

    if media_type == "application/pdf":
        page_count = _get_page_count(content)
        if page_count > _MAX_PAGES:
            raise ValueError(f"too_many_pages: {filename!r} has {page_count} pages; limit is {_MAX_PAGES}")
        for page_idx in range(page_count):
            try:
                image_b64 = _pdf_page_to_base64_png(content, page_idx)
                raw_list = _call_vision_api_intake(image_b64, "image/png", patient_uuid_hash)
                blocks = _extract_text_blocks_pdfplumber(content, page_idx)
                for raw in raw_list:
                    field = _process_raw_intake_field(raw, page_idx, blocks, doc_sha, patient_uuid_hash)
                    if field:
                        all_fields.append(field)
            except Exception as exc:
                logger.error("Error processing page %d of %r: %s", page_idx, filename, exc)
    else:
        # Image-only (PNG/JPEG)
        try:
            image_b64, effective_type = _image_to_base64_png(content, media_type)
            raw_list = _call_vision_api_intake(image_b64, effective_type, patient_uuid_hash)
            for raw in raw_list:
                field = _process_raw_intake_field(raw, 0, [], doc_sha, patient_uuid_hash)
                if field:
                    all_fields.append(field)
        except Exception as exc:
            logger.error("Image intake extraction failed for %r: %s", filename, exc)

    return {
        "doc_type": "intake_form",
        "document_sha256": doc_sha,
        "patient_uuid_hash": patient_uuid_hash,
        "filename": filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extracted_by": _MODEL,
        "extracted_field_count": len(all_fields),
        "result": {"fields": all_fields},
    }
