"""Lab PDF extractor — Workstream A (Plan §6).

Pipeline:
  1. In eval mode: return deterministic fixtures from _eval_mocks_a.
  2. In live mode:
     a. Render each PDF page to a base64 PNG via pypdfium2.
     b. Extract word-level bboxes from the text layer via pdfplumber.
     c. Call Anthropic Vision (COPILOT_VISION_MODEL, default claude-sonnet-4-6)
        to extract field dicts.
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
_MODEL = os.getenv("COPILOT_VISION_MODEL", "claude-sonnet-4-6")
_BBOX_UNIT = "exact"

_LAB_TEXT_ROW_PATTERNS: tuple[tuple[str, str], ...] = (
    ("total_cholesterol", r"Cholesterol,\s*Total"),
    ("hdl", r"HDL\s+Cholesterol"),
    ("ldl", r"LDL\s+Cholesterol,?(?:\s+Calculated)?"),
    ("triglycerides", r"Triglycerides"),
    ("non_hdl_cholesterol", r"Non-HDL\s+Cholesterol"),
    ("hba1c", r"(?:HbA1c|Hemoglobin\s+A1c|A1c)"),
    ("wbc", r"WBC"),
    ("rbc", r"RBC"),
    ("hemoglobin", r"Hemoglobin"),
    ("hematocrit", r"Hematocrit"),
    ("platelets", r"Platelets"),
    ("sodium", r"Sodium"),
    ("potassium", r"Potassium"),
    ("creatinine", r"Creatinine"),
    ("bun", r"BUN"),
    ("glucose", r"Glucose"),
)
_LAB_UNIT_RE = re.compile(r"\b(mg/dL|g/dL|K/uL|M/uL|mEq/L|mmol/L|%|IU/L|U/L)\b")


def _normalize_bbox_value(value: float, axis_max: float) -> float:
    if abs(value) > 1.0 and axis_max > 0:
        value = value / axis_max
    return min(max(value, 0.0), 1.0)


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
            page_width = max(float(matched[0].get("page_width") or 1.0), 1.0)
            page_height = max(float(matched[0].get("page_height") or 1.0), 1.0)
            return (
                round(_normalize_bbox_value(float(x0), page_width), 6),
                round(_normalize_bbox_value(float(y0), page_height), 6),
                round(_normalize_bbox_value(float(x1), page_width), 6),
                round(_normalize_bbox_value(float(y1), page_height), 6),
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


def _extract_pdf_page_text_and_blocks(
    pdf_bytes: bytes,
    page_index: int,
    page_width: float,
    page_height: float,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_index >= len(pdf.pages):
                return "", []
            page = pdf.pages[page_index]
            words = page.extract_words()
            blocks = []
            for word in words:
                if page_width > 0 and page_height > 0:
                    blocks.append({
                        "text": word["text"],
                        "x0": word["x0"] / page_width,
                        "y0": word["top"] / page_height,
                        "x1": word["x1"] / page_width,
                        "y1": word["bottom"] / page_height,
                    })
            text = page.extract_text() or " ".join(str(w.get("text", "")) for w in words)
            return text.strip(), blocks
    except Exception as exc:
        logger.warning("pdfplumber text extraction failed on page %d: %s", page_index, exc)
        return "", []


def _has_meaningful_text_layer(page_text: str) -> bool:
    words = [w for w in page_text.split() if any(ch.isalnum() for ch in w)]
    return len(words) >= 8


def _extract_lab_fields_from_text(page_text: str) -> list[dict[str, Any]]:
    """Recover common table-shaped lab rows from a PDF text layer."""

    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines()]
    for line in lines:
        if not line:
            continue
        for name, label_pattern in _LAB_TEXT_ROW_PATTERNS:
            if name in seen:
                continue
            match = re.search(
                rf"^{label_pattern}\s+(?P<value>[<>]?\d+(?:\.\d+)?)\s*(?P<flag>[HL])?\b(?P<tail>.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if match is None:
                continue
            tail = match.group("tail") or ""
            unit_match = _LAB_UNIT_RE.search(tail)
            fields.append({
                "name": name,
                "value": match.group("value"),
                "unit": unit_match.group(1) if unit_match else None,
                "abnormal": bool(match.group("flag")),
                "flag": match.group("flag") or None,
                "quote_or_value": line,
                "confidence": 0.92,
            })
            seen.add(name)
            break
    return fields


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


def _call_vision_api_once(
    image_b64: str | None,
    patient_uuid_hash: str,
    *,
    page_text: str | None = None,
    repair_errors: list[str] | None = None,
    prior_raw: str = "",
) -> tuple[list[dict[str, Any]] | None, list[str], str]:
    import anthropic  # type: ignore[import-untyped]

    from app.extractors.anthropic_tools import (
        EXTRACT_FIELDS_TOOL_NAME,
        extraction_fields_tool,
        parse_extracted_fields_tool,
    )

    client = anthropic.Anthropic()
    system = (
        "You are a clinical lab document parser. Extract structured lab results. "
        f"Use the {EXTRACT_FIELDS_TOOL_NAME} tool. Extract an object with a fields array. "
        "Each field has: name (snake_case field name), "
        "value (numeric or string), unit (string or null), abnormal (bool), "
        "quote_or_value (verbatim text from document, max 60 chars). "
        "Only include fields visible in the image. No hallucination."
    )
    prompt = (
        "Extract all lab result fields from this page using the tool. "
        "The tool input must be an object with a fields array."
    )
    if page_text:
        prompt += (
            "\nThis PDF page has a text layer. Use the page text below as the primary source, "
            "and choose quote_or_value from verbatim nearby text.\n\nPAGE TEXT:\n"
            + page_text[:12000]
        )
    if repair_errors:
        prompt = (
            "Your previous extraction response failed validation:\n- "
            + "\n- ".join(repair_errors[:5])
            + "\nReturn a corrected extraction using the same tool. "
            "Do not invent missing values; emit fields=[] if no supported lab fields are visible."
        )
        if page_text:
            prompt += "\n\nPAGE TEXT:\n" + page_text[:12000]
        if prior_raw:
            prompt += "\nPrevious non-tool text was ignored."
    content: list[dict[str, Any]] = []
    if image_b64:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}})
    content.append({"type": "text", "text": prompt})
    response = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        tools=[extraction_fields_tool()],
        tool_choice={"type": "tool", "name": EXTRACT_FIELDS_TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
    )
    return parse_extracted_fields_tool(response)


def _call_vision_api(image_b64: str | None, patient_uuid_hash: str, page_text: str | None = None) -> list[dict[str, Any]]:
    fields, errors, raw_text = _call_vision_api_once(image_b64, patient_uuid_hash, page_text=page_text)
    if fields is not None:
        return fields

    logger.warning(
        "lab_pdf structured extraction retrying after invalid tool payload: %s",
        "; ".join(errors),
    )
    repaired, repair_errors, _ = _call_vision_api_once(
        image_b64,
        patient_uuid_hash,
        page_text=page_text,
        repair_errors=errors,
        prior_raw=raw_text,
    )
    if repaired is not None:
        return repaired
    raise ValueError(
        "extraction_failed: lab_pdf model did not emit valid structured fields ("
        + "; ".join(repair_errors or errors)
        + ")"
    )


def extract_lab_pdf(
    pdf_bytes: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "upload.pdf",
) -> dict[str, Any]:
    from app.extractors.normalize import normalize_extracted_document
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
        payload = {
            "doc_type": "lab_pdf",
            "document_sha256": doc_sha,
            "patient_uuid_hash": patient_uuid_hash,
            "filename": filename,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extracted_by": "eval-mock",
            "extracted_field_count": len(fields),
            "result": {"fields": fields},
        }
        return normalize_extracted_document(
            payload,
            doc_type="lab_pdf",
            document_sha256=doc_sha,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )

    # Live mode
    page_count = _get_page_count(pdf_bytes)
    if page_count > _MAX_PAGES:
        raise ValueError(f"too_many_pages: {filename!r} has {page_count} pages; maximum is {_MAX_PAGES}")

    all_fields: list[dict[str, Any]] = []
    page_errors: list[str] = []
    for page_idx in range(page_count):
        try:
            width, height = _get_page_dimensions(pdf_bytes, page_idx)
            page_text, blocks = _extract_pdf_page_text_and_blocks(pdf_bytes, page_idx, width, height)
            if _has_meaningful_text_layer(page_text):
                raw_fields = _extract_lab_fields_from_text(page_text)
                if not raw_fields:
                    raw_fields = _call_vision_api(None, patient_uuid_hash, page_text=page_text)
            else:
                image_b64 = _page_to_base64_png(pdf_bytes, page_idx)
                raw_fields = _call_vision_api(image_b64, patient_uuid_hash)
                if not blocks:
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
            page_errors.append(str(exc))
            logger.error(
                "Error processing lab PDF page %d for document %s: %s",
                page_idx,
                doc_sha[:12],
                exc,
            )

    if not all_fields and page_errors:
        raise ValueError("extraction_failed: " + "; ".join(page_errors[:3]))

    payload = {
        "doc_type": "lab_pdf",
        "document_sha256": doc_sha,
        "patient_uuid_hash": patient_uuid_hash,
        "filename": filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extracted_by": _MODEL,
        "extracted_field_count": len(all_fields),
        "result": {"fields": all_fields},
    }
    return normalize_extracted_document(
        payload,
        doc_type="lab_pdf",
        document_sha256=doc_sha,
        patient_uuid_hash=patient_uuid_hash,
        filename=filename,
    )
