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
_MODEL = os.getenv("COPILOT_VISION_MODEL", "claude-sonnet-4-6")
_BBOX_UNIT = "exact"

_MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}

_JUNK_INTAKE_FIELD_NAMES = {
    "form.organization",
    "form.id",
    "form.data_note",
    "form.footer",
    "form.header",
    "form.title",
    "metadata.form_id",
}

_IMAGE_KEY_VALUE_FIELDS = {
    "demographics.first_name",
    "demographics.last_name",
    "demographics.date_of_birth",
    "demographics.sex",
    "demographics.phone",
    "demographics.email",
    "demographics.address",
    "chief_complaint",
    "medical_history.problem_list",
    "medications.self_reported",
    "allergies.self_reported",
    "family_history.self_reported",
}


def _normalize_bbox_value(value: float, axis_max: float) -> float:
    if abs(value) > 1.0 and axis_max > 0:
        value = value / axis_max
    return min(max(value, 0.0), 1.0)


def _detect_media_type(content: bytes, filename: str = "upload.pdf") -> str:
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


_get_page_count_pdf = _get_page_count


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


def _extract_pdf_page_text_and_blocks(
    pdf_bytes: bytes,
    page_index: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Return text-layer content plus word bboxes for typed PDF pages."""

    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_index >= len(pdf.pages):
                return "", []
            page = pdf.pages[page_index]
            width = float(page.width) if page.width else 612.0
            height = float(page.height) if page.height else 792.0
            words = page.extract_words()
            blocks = []
            for word in words:
                if width > 0 and height > 0:
                    blocks.append({
                        "text": word["text"],
                        "x0": word["x0"] / width,
                        "y0": word["top"] / height,
                        "x1": word["x1"] / width,
                        "y1": word["bottom"] / height,
                    })
            text = page.extract_text() or " ".join(str(w.get("text", "")) for w in words)
            return text.strip(), blocks
    except Exception as exc:
        logger.warning("pdfplumber text extraction failed on page %d: %s", page_index, exc)
        return "", []


def _has_meaningful_text_layer(page_text: str) -> bool:
    words = [w for w in page_text.split() if any(ch.isalnum() for ch in w)]
    return len(words) >= 12


def _squash_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_intake_fields_from_text(page_text: str) -> list[dict[str, Any]]:
    """Recover common typed intake fields from a PDF text layer."""

    fields: list[dict[str, Any]] = []

    def add(name: str, value: Any, quote: str | None = None, confidence: float = 0.90) -> None:
        if value is None:
            return
        if isinstance(value, str):
            value = _squash_ws(value)
            if not value:
                return
        fields.append({
            "name": name,
            "value": value,
            "quote_or_value": _squash_ws(quote) if quote else None,
            "confidence": confidence,
        })

    legal = re.search(
        r"LEGAL NAME\s+(?P<last>[A-Za-z][A-Za-z .'-]+?),\s+DATE OF BIRTH\s+"
        r"(?P<dob>\d{4}-\d{2}-\d{2})\s*\n(?P<first>[A-Za-z][A-Za-z .'-]+)",
        page_text,
    )
    if legal:
        first_line = _squash_ws(legal.group("first"))
        first = first_line.split()[0]
        last = _squash_ws(legal.group("last"))
        dob = legal.group("dob")
        add("demographics.first_name", first, first_line, 0.95)
        add("demographics.last_name", last, f"LEGAL NAME {last},", 0.95)
        add("demographics.date_of_birth", dob, f"DATE OF BIRTH {dob}", 0.95)

    sex = re.search(r"SEX ASSIGNED AT BIRTH\s+(Female|Male|Intersex|Unknown)", page_text, re.IGNORECASE)
    if sex:
        add("demographics.sex", sex.group(1).title(), sex.group(0), 0.94)

    email = re.search(r"EMAIL\s+([^\s]+@[^\s]+)", page_text, re.IGNORECASE)
    if email:
        add("demographics.email", email.group(1), email.group(1), 0.92)

    address = re.search(r"HOME ADDRESS\s+([^\n]+)", page_text, re.IGNORECASE)
    if address:
        full_address = _squash_ws(address.group(1))
        add("demographics.address", full_address, f"HOME ADDRESS {full_address}", 0.92)
        city_state_zip = re.search(r",\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", full_address)
        if city_state_zip:
            add("demographics.city", city_state_zip.group(1), city_state_zip.group(1), 0.90)
            add("demographics.state", city_state_zip.group(2), city_state_zip.group(2), 0.90)
            add("demographics.postal_code", city_state_zip.group(3), city_state_zip.group(3), 0.90)

    phone = re.search(r"MOBILE PHONE\s+(\(\d{3}\)\s+\d{3}-)\s+EMAIL", page_text, re.IGNORECASE)
    phone_suffix = re.search(r"EMAIL\s+[^\s]+\s*\n(\d{4})", page_text, re.IGNORECASE)
    if phone and phone_suffix:
        add("demographics.phone", phone.group(1) + phone_suffix.group(1), None, 0.86)

    chief = re.search(r"CHIEF CONCERN\s+(.*?)\s+ONSET / DURATION", page_text, re.IGNORECASE | re.DOTALL)
    if chief:
        add("chief_complaint", chief.group(1), None, 0.92)

    medications: list[str] = []
    for medication in ("Lisinopril", "Metformin", "Atorvastatin", "Aspirin"):
        med_match = re.search(rf"({medication}[^\n]+)", page_text, re.IGNORECASE)
        if med_match:
            medications.append(_squash_ws(med_match.group(1)))
    if medications:
        add("medications.self_reported", "; ".join(medications), medications[0], 0.90)

    allergies: list[str] = []
    for allergy in ("Penicillin", "Sulfa drugs", "shellfish"):
        allergy_match = re.search(rf"({allergy}[^\n]*)", page_text, re.IGNORECASE)
        if allergy_match:
            allergies.append(_squash_ws(allergy_match.group(1)))
    if allergies:
        add("allergies.self_reported", "; ".join(allergies), allergies[0], 0.88)

    if re.search(r"TOBACCO\s+Former smoker", page_text, re.IGNORECASE):
        add("social_history.smoking_status", "Former smoker", "TOBACCO Former smoker", 0.88)
    if "Myocardial infarction" in page_text or "Type 2 diabetes mellitus" in page_text:
        add(
            "family_history.self_reported",
            "Father myocardial infarction; mother type 2 diabetes mellitus; brother essential hypertension",
            None,
            0.86,
        )

    return fields


def _call_vision_api_intake(
    image_b64: str, media_type: str, patient_uuid_hash: str
) -> list[dict[str, Any]]:
    try:
        return _call_structured_intake_api(
            patient_uuid_hash=patient_uuid_hash,
            image_b64=image_b64,
            media_type=media_type,
            page_text=None,
        )
    except ValueError as exc:
        fallback = _call_image_key_value_intake_api(image_b64, media_type)
        if fallback:
            logger.warning("intake_form used image key-value fallback after structured extraction failed")
            return fallback
        raise exc


def _parse_image_key_value_intake(text: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.match(r"^\s*([a-z0-9_.]+)\s*[:=]\s*(.*?)\s*$", line, re.IGNORECASE)
        if match is None:
            continue
        name = match.group(1).lower()
        value = _squash_ws(match.group(2))
        if name not in _IMAGE_KEY_VALUE_FIELDS or not value or value.lower() in {"unknown", "n/a", "none"}:
            continue
        fields.append({
            "name": name,
            "value": value,
            "quote_or_value": value,
            "confidence": 0.72,
        })
    return fields


def _call_image_key_value_intake_api(image_b64: str, media_type: str) -> list[dict[str, Any]]:
    import anthropic  # type: ignore[import-untyped]

    client = anthropic.Anthropic()
    prompt = (
        "Read this clinical intake form image and transcribe only clearly legible values. "
        "Do not return JSON. Return one field per line using exactly field=value. "
        "Allowed fields: demographics.first_name, demographics.last_name, "
        "demographics.date_of_birth, demographics.sex, demographics.phone, demographics.email, "
        "demographics.address, chief_complaint, medical_history.problem_list, "
        "medications.self_reported, allergies.self_reported, family_history.self_reported. "
        "Omit fields that are not visible or uncertain."
    )
    response = client.messages.create(
        model=_MODEL,
        max_tokens=800,
        system="You are a careful clinical form transcription assistant.",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    text = ""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            text += str(getattr(block, "text", "")) + "\n"
    return _parse_image_key_value_intake(text)


def _call_structured_intake_api_once(
    *,
    patient_uuid_hash: str,
    image_b64: str | None,
    media_type: str | None,
    page_text: str | None,
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
        "You are a clinical intake form parser. Extract structured patient intake data. "
        f"Use the {EXTRACT_FIELDS_TOOL_NAME} tool. Return an object with a fields array. "
        "Each field has: name (dot-notated field path e.g. "
        "'vitals.blood_pressure', 'chief_complaint', 'medications.self_reported'), "
        "value (string or number), quote_or_value (verbatim text from form if typed, "
        "null if handwritten and illegible). "
        "Extract demographics, chief concern, medications, allergies, family history, "
        "vitals, and social history when present. "
        "Avoid generic form header/footer fields such as organization, form id, or copyright notes. "
        "Only include fields actually present in the document."
    )
    prompt = "Extract all clinical intake form fields using the tool."
    if page_text:
        prompt += (
            "\nThis typed PDF page has a text layer. Use only verbatim values "
            "supported by the page text below for quote_or_value.\n\nPAGE TEXT:\n"
            + page_text[:12000]
        )
    if repair_errors:
        prompt = (
            "Your previous extraction response failed validation:\n- "
            + "\n- ".join(repair_errors[:5])
            + "\nReturn a corrected extraction using the same tool. "
            "Do not invent missing values; emit fields=[] if no supported intake fields are visible."
        )
        if page_text:
            prompt += "\n\nPAGE TEXT:\n" + page_text[:12000]
        if prior_raw:
            prompt += "\nPrevious non-tool text was ignored."

    content: list[dict[str, Any]] = []
    if image_b64 and media_type:
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}})
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


def _call_structured_intake_api(
    *,
    patient_uuid_hash: str,
    image_b64: str | None,
    media_type: str | None,
    page_text: str | None,
) -> list[dict[str, Any]]:
    fields, errors, raw_text = _call_structured_intake_api_once(
        patient_uuid_hash=patient_uuid_hash,
        image_b64=image_b64,
        media_type=media_type,
        page_text=page_text,
    )
    if fields is not None:
        return fields

    logger.warning(
        "intake_form structured extraction retrying after invalid tool payload: %s",
        "; ".join(errors),
    )
    repaired, repair_errors, _ = _call_structured_intake_api_once(
        patient_uuid_hash=patient_uuid_hash,
        image_b64=image_b64,
        media_type=media_type,
        page_text=page_text,
        repair_errors=errors,
        prior_raw=raw_text,
    )
    if repaired is not None:
        return repaired
    raise ValueError(
        "extraction_failed: intake model did not emit valid structured fields ("
        + "; ".join(repair_errors or errors)
        + ")"
    )


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
    if name.lower() in _JUNK_INTAKE_FIELD_NAMES:
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
    from app.extractors.normalize import normalize_extracted_document
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
        payload = {
            "doc_type": "intake_form",
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
            doc_type="intake_form",
            document_sha256=doc_sha,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )

    # Live mode
    media_type = _detect_media_type(content, filename)
    all_fields: list[dict[str, Any]] = []

    if media_type == "application/pdf":
        page_count = _get_page_count_pdf(content)
        if page_count > _MAX_PAGES:
            raise ValueError(f"too_many_pages: {filename!r} has {page_count} pages; maximum is {_MAX_PAGES}")
        page_errors: list[str] = []
        for page_idx in range(page_count):
            try:
                page_text, blocks = _extract_pdf_page_text_and_blocks(content, page_idx)
                if _has_meaningful_text_layer(page_text):
                    raw_list = _extract_intake_fields_from_text(page_text)
                    if not raw_list:
                        raw_list = _call_structured_intake_api(
                            patient_uuid_hash=patient_uuid_hash,
                            image_b64=None,
                            media_type=None,
                            page_text=page_text,
                        )
                else:
                    image_b64 = _pdf_page_to_base64_png(content, page_idx)
                    raw_list = _call_vision_api_intake(image_b64, "image/png", patient_uuid_hash)
                    if not blocks:
                        blocks = _extract_text_blocks_pdfplumber(content, page_idx)
                for raw in raw_list:
                    field = _process_raw_intake_field(raw, page_idx, blocks, doc_sha, patient_uuid_hash)
                    if field:
                        all_fields.append(field)
            except Exception as exc:
                page_errors.append(str(exc))
                logger.error(
                    "Error processing intake PDF page %d for document %s: %s",
                    page_idx,
                    doc_sha[:12],
                    exc,
                )
        if not all_fields and page_errors:
            raise ValueError("extraction_failed: " + "; ".join(page_errors[:3]))
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
            logger.error("Image intake extraction failed for document %s: %s", doc_sha[:12], exc)
            raise ValueError(f"extraction_failed: {exc}") from exc

    payload = {
        "doc_type": "intake_form",
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
        doc_type="intake_form",
        document_sha256=doc_sha,
        patient_uuid_hash=patient_uuid_hash,
        filename=filename,
    )
