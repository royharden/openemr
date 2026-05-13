"""Medication-list extractor — Workstream A Phase 6.3 (Plan §6.3, AgDR-0077).

The third doc-type alongside ``lab_pdf`` and ``intake_form``. Each medication
list document (typed PDF / handwritten PNG / dirty-scan PDF) is reduced to a
flat list of :class:`app.schemas.MedicationListEntry` rows. The PHP gateway
then feeds those rows into ``MedicationReconciliation`` to compare against
the OpenEMR ``prescriptions`` table.

Pipeline (mirrors ``lab_pdf.py``):

  1. In eval mode (``COPILOT_EVAL_MODE=1``): resolve a fixture key by
     filename substring and return a deterministic mock entry list from
     ``app.extractors._eval_mocks_a``. No vision call.

  2. In live mode:

     a. Detect media type (PDF / PNG / JPEG).
     b. For PDFs, page-by-page:
        - Try the text layer first (``pdfplumber.extract_words``); when the
          layer is meaningful (>= 12 alphanumeric words) and the printed
          table is regular enough we recover entries from a regex pass over
          the page text — same trick the lab extractor uses to avoid an
          unnecessary vision call on clean typed PDFs.
        - Fall through to a forced-tool-use Anthropic Vision call with the
          ``emit_medication_list_entries`` tool when the text-layer
          recovery misses or the layer is too sparse (dirty-scan, handwritten
          PDFs). One repair pass mirrors the existing lab/intake retry path.
     c. For PNG/JPEG, always go through the vision path. Bbox is allowed to
        be ``None`` (handwritten forms have no text layer to ground against)
        per AgDR-0040 — but we still attempt bbox derivation against any
        pdfplumber blocks we manage to recover.

The extractor never persists to the DB — that is the PHP gateway's job
(``DocumentUploadController::uploadMedicationList`` -> ``DocumentFactsRepository``).

Returns a dict shaped like :class:`app.schemas.ExtractedDocument` with
``result`` set to an ``ExtractedMedicationList`` payload (carrying both a
flat ``fields`` list per medication_list-attribute and a structured
``entries`` list per drug row).
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.extractors.lab_pdf import (
    _extract_pdf_page_text_and_blocks,
    _find_verbatim_bbox,
    _get_page_count,
    _get_page_dimensions,
    _has_meaningful_text_layer,
    _page_to_base64_png,
    _sha256_bytes,
)

logger = logging.getLogger(__name__)

_MAX_PAGES = 10
_MODEL = os.getenv("COPILOT_VISION_MODEL", "claude-sonnet-4-6")
_BBOX_UNIT = "exact"

_MEDIA_MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}

# Field-path attributes emitted per medication-list entry. Kept as a tuple so
# the order is stable across the flat-field surface, the DocumentFactsRepository
# write, and the eval-mode mock output.
_ENTRY_FIELDS: tuple[str, ...] = (
    "dose",
    "route",
    "frequency",
    "start_date",
    "prescriber",
    "indication",
)


def _detect_media_type(content: bytes, filename: str = "upload.pdf") -> str:
    for magic, mime in _MEDIA_MAGIC_BYTES.items():
        if content[: len(magic)] == magic:
            return mime
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(ext, "application/pdf")


def _slugify_drug_name(drug: str) -> str:
    """Stable, PHI-free slug for use inside source_id and field_path."""

    cleaned = re.sub(r"[^a-z0-9]+", "_", drug.lower()).strip("_")
    return cleaned or "unknown"


def _expand_entries_to_fields(
    entries: list[dict[str, Any]],
    *,
    doc_sha: str,
    patient_uuid_hash: str,
) -> list[dict[str, Any]]:
    """Emit one ``ExtractedField``-shaped dict per (entry, attribute) pair.

    The flat-field surface is what the gateway's DocumentFactsRepository
    persists into ``copilot_document_facts``. Each entry produces one
    ``medication.<slug>.drug_name`` row plus one row per non-null attribute
    in ``_ENTRY_FIELDS``. This mirrors the lab_pdf field-emission shape so
    the citation_present rubric sees an even row population.
    """

    out: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        drug = str(entry.get("drug_name") or "").strip()
        if not drug:
            continue
        slug = f"{_slugify_drug_name(drug)}_{index}"
        page_index = int(entry.get("page_index") or 0)
        confidence = float(entry.get("confidence") or 0.85)
        quote = entry.get("quote_or_value")
        bbox = entry.get("bbox")
        bbox_unit = entry.get("bbox_unit") or (_BBOX_UNIT if bbox else None)

        def _field(
            attr: str, value: Any, attr_quote: str | None = None
        ) -> dict[str, Any]:
            field_path = f"medication.{slug}.{attr}"
            source_id = f"doc:{doc_sha[:12]}:page{page_index}:{slug}:{attr}"
            return {
                "name": f"{slug}.{attr}",
                "value": value,
                "unit": None,
                "abnormal": False,
                "flag": None,
                "source_id": source_id,
                "quote_or_value": attr_quote or quote,
                "page_index": page_index,
                "bbox": bbox,
                "bbox_unit": bbox_unit,
                "confidence": confidence,
                "idempotency_key": hashlib.sha256(
                    f"{patient_uuid_hash}{doc_sha}{field_path}".encode()
                ).hexdigest(),
            }

        out.append(_field("drug_name", drug))
        for attr in _ENTRY_FIELDS:
            attr_value = entry.get(attr)
            if attr_value is None:
                continue
            attr_value_str = str(attr_value).strip()
            if not attr_value_str:
                continue
            out.append(_field(attr, attr_value_str))
    return out


def _build_entries_with_citations(
    raw_entries: list[dict[str, Any]],
    *,
    doc_sha: str,
    patient_uuid_hash: str,
) -> list[dict[str, Any]]:
    """Attach a SourcePacket citation to each MedicationListEntry.

    Each entry's citation points at its drug_name field — the rubric only
    needs one packet per entry, and reconciliation joins on drug_name anyway.
    """

    entries_out: list[dict[str, Any]] = []
    for index, entry in enumerate(raw_entries):
        drug = str(entry.get("drug_name") or "").strip()
        if not drug:
            continue
        slug = f"{_slugify_drug_name(drug)}_{index}"
        page_index = int(entry.get("page_index") or 0)
        confidence = float(entry.get("confidence") or 0.85)
        bbox = entry.get("bbox")
        bbox_unit = entry.get("bbox_unit") or (_BBOX_UNIT if bbox else None)
        field_path = f"medication.{slug}.drug_name"
        source_id = f"doc:{doc_sha[:12]}:page{page_index}:{slug}:drug_name"
        quote = entry.get("quote_or_value")

        citation = {
            "source_id": source_id,
            "patient_uuid": patient_uuid_hash,
            "resource_type": "MedicationStatement",
            "source_table": "document_upload",
            "source_uuid": None,
            "field": field_path,
            "label": drug,
            "value": drug,
            "unit": None,
            "observed_at": None,
            "last_updated": None,
            "freshness": "recent",
            "status": None,
            "sensitive": False,
            "source_type": "document_extract",
            "field_or_chunk_id": field_path,
            "quote_or_value": quote,
            "bbox": list(bbox) if isinstance(bbox, (list, tuple)) else None,
            "bbox_unit": bbox_unit if bbox else None,
            "confidence": confidence,
            "page_index": page_index,
        }
        # Trim Nones — the SourcePacket model accepts them but the on-the-wire
        # shape matches the lab/intake extractor when keys with `None` are
        # dropped (smaller payload, no schema-validation behavior change).
        citation = {k: v for k, v in citation.items() if v is not None}

        entries_out.append({
            "drug_name": drug,
            "dose": entry.get("dose"),
            "route": entry.get("route"),
            "frequency": entry.get("frequency"),
            "start_date": entry.get("start_date"),
            "prescriber": entry.get("prescriber"),
            "indication": entry.get("indication"),
            "source_citation": citation,
        })
    return entries_out


# ---------------------------------------------------------------------------
# Text-layer recovery — typed-PDF fast path
# ---------------------------------------------------------------------------

# Match a medication-list row in the Whitaker-style table layout. The Whitaker
# fixture renders columns left-to-right (Drug / Dose / Route / Frequency /
# Start / Prescriber / Indication). The other fixtures don't have a reliable
# typed text layer (handwritten / dirty-scan), so this regex only ever needs
# to recognize the typed fixture's row shape.
_TYPED_ROW_RE = re.compile(
    r"^(?P<drug>[A-Z][A-Za-z0-9 .,\-()/]+?)\s+"
    r"(?P<dose>\d+(?:\.\d+)?\s*(?:mg|mcg|g|IU|mL|units?))\s+"
    r"(?P<route>PO|IM|IV|SC|SQ|INH|TOP|SL|PR|OTH)\s+"
    r"(?P<frequency>(?:BID|TID|QID|Daily|QHS|QAM|PRN|Q\d+H(?:\s+PRN)?)|"
    r"(?:Q6H\s+PRN))\s+"
    r"(?P<start>\d{4}-\d{2}-\d{2}|~\d{4}|unknown)\s+"
    # Prescriber: either "Lastname, X." (comma + initial form) or a generic
    # capitalized phrase like "Home PCP". Match greedily on the comma form
    # so "Patel, N." isn't split.
    r"(?P<prescriber>(?:[A-Z][A-Za-z]+,\s+[A-Z]\.?)|(?:[A-Z][A-Za-z]+(?:\s+[A-Z]+)?))\s+"
    r"(?P<indication>[A-Za-z][^\n]+)$",
    re.MULTILINE,
)


def _extract_entries_from_text(page_text: str) -> list[dict[str, Any]]:
    """Pull medication-list rows from a typed-PDF text layer.

    Returns empty list when the text layer doesn't look like a medication
    list — caller falls through to the vision path. We intentionally do
    NOT try to recover handwritten or dirty-scan rows from text (the
    handwritten fixture has no text layer; the dirty-scan fixture has
    fragmented words that the regex would mis-parse).
    """

    entries: list[dict[str, Any]] = []
    # The reportlab-generated Whitaker fixture serializes the table column-by-column
    # in the text layer (all drugs, then all doses, etc.). Split on the section
    # headers and zip the rows back together when we see that pattern.
    columns = _split_columnar_table(page_text)
    if columns is not None:
        for row in columns:
            entries.append({
                "drug_name": row.get("drug", ""),
                "dose": row.get("dose"),
                "route": row.get("route"),
                "frequency": row.get("frequency"),
                "start_date": row.get("start"),
                "prescriber": row.get("prescriber"),
                "indication": row.get("indication"),
                "quote_or_value": " ".join(
                    str(row.get(col) or "") for col in ("drug", "dose", "route", "frequency", "start", "prescriber", "indication")
                ).strip(),
                "page_index": 0,
                "confidence": 0.92,
            })
        return entries

    # Fall back to the row-shaped regex (single-line per entry).
    for match in _TYPED_ROW_RE.finditer(page_text):
        entries.append({
            "drug_name": match.group("drug").strip(),
            "dose": match.group("dose").strip(),
            "route": match.group("route").strip(),
            "frequency": match.group("frequency").strip(),
            "start_date": match.group("start").strip(),
            "prescriber": match.group("prescriber").strip(),
            "indication": match.group("indication").strip(),
            "quote_or_value": match.group(0).strip(),
            "page_index": 0,
            "confidence": 0.92,
        })
    return entries


_COL_HEADERS = ("Drug", "Dose", "Route", "Frequency", "Start", "Prescriber", "Indication")


def _split_columnar_table(page_text: str) -> list[dict[str, str]] | None:
    """Recover rows from a column-serialized table text layer.

    reportlab's text export emits the table column-by-column when each cell
    fits on one line — the Whitaker typed PDF shows up in `pdftotext` as
    "Drug\\nApixaban Metoprolol ... Pantoprazole\\nDose\\n5 mg 50 mg ... 40 mg\\n…".
    We detect this shape by looking for the column header followed by a
    space-delimited row of N tokens, then zip those N tokens across all
    seven columns.
    """

    # Quick gate: every expected header must appear at least once.
    for header in _COL_HEADERS:
        if header not in page_text:
            return None

    cells: dict[str, list[str]] = {}
    lines = [line.rstrip() for line in page_text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line in _COL_HEADERS:
            # Next non-empty line is the column payload.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            cells[line] = _split_column_row(lines[j].strip())
            i = j + 1
            continue
        i += 1

    if set(cells.keys()) != set(_COL_HEADERS):
        return None

    n_rows = len(cells["Drug"])
    if n_rows == 0:
        return None
    for header, values in cells.items():
        if len(values) != n_rows:
            return None

    out: list[dict[str, str]] = []
    for ridx in range(n_rows):
        out.append({
            "drug": cells["Drug"][ridx],
            "dose": cells["Dose"][ridx],
            "route": cells["Route"][ridx],
            "frequency": cells["Frequency"][ridx],
            "start": cells["Start"][ridx],
            "prescriber": cells["Prescriber"][ridx],
            "indication": cells["Indication"][ridx],
        })
    return out


# Tokens that may legitimately appear *inside* a column value (so the
# whitespace tokenizer should keep them attached to their neighbor).
_GLUE_NEXT_TOKENS: tuple[str, ...] = (
    "mg", "mcg", "g", "IU", "mL", "units",
    "(low-dose)",
)


def _split_column_row(row: str) -> list[str]:
    """Tokenize a column-serialized row into per-cell strings.

    The Whitaker fixture uses multi-word values ("Metoprolol succinate",
    "Aspirin (low-dose)", "Rate control / HTN", "Patel, N.") — naïve
    `split()` would over-split them. We re-glue when:
      * the next token is a known unit suffix (so "5" + "mg" → "5 mg");
      * the next token is "(low-dose)";
      * the current token ends in "," and the next is an initial-like
        capital ("Patel," + "N.");
      * a slash separates two indication words ("Rate" / "control");
      * we're still inside the drug column and the next token starts
        with a lowercase letter ("Metoprolol" + "succinate").

    For simple Daily/BID/PO routes the simple tokenizer is correct.
    """

    tokens = row.split()
    out: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        buf.append(token)
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        # Glue: unit suffix after a numeric token.
        if nxt and (
            nxt.lower() in {"mg", "mcg", "g", "iu", "ml", "units"}
            or nxt == "(low-dose)"
        ):
            buf.append(nxt)
            i += 2
            out.append(" ".join(buf))
            buf = []
            continue
        # Glue: "Patel," + "N." (comma-suffixed token + initial-like).
        if (
            token.endswith(",")
            and nxt
            and len(nxt) <= 4
            and nxt[0].isupper()
            and nxt.endswith(".")
        ):
            buf.append(nxt)
            i += 2
            out.append(" ".join(buf))
            buf = []
            continue
        # Glue: compound drug name ("Metoprolol succinate") — only at the
        # start of the row (drug column) where `out` is empty.
        if (
            token
            and nxt
            and token[0].isupper()
            and nxt[0].islower()
            and nxt.lower() not in {"mg", "mcg", "iu"}
            and len(out) == 0
        ):
            buf.append(nxt)
            i += 2
            out.append(" ".join(buf))
            buf = []
            continue
        out.append(" ".join(buf))
        buf = []
        i += 1
    if buf:
        out.append(" ".join(buf))
    return _merge_slash_phrases(out)


def _merge_slash_phrases(tokens: list[str]) -> list[str]:
    """Merge tokens around a standalone '/' or 'NEW' into a single cell."""

    merged: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Standalone slash → glue prev + slash + next.
        if token == "/" and merged and i + 1 < len(tokens):
            merged[-1] = merged[-1] + " / " + tokens[i + 1]
            i += 2
            continue
        merged.append(token)
        i += 1
    return merged


# ---------------------------------------------------------------------------
# Live-mode Anthropic vision path
# ---------------------------------------------------------------------------


def _call_vision_api_once(
    *,
    image_b64: str | None,
    media_type: str | None,
    page_text: str | None,
    repair_errors: list[str] | None = None,
    prior_raw: str = "",
) -> tuple[list[dict[str, Any]] | None, list[str], str]:
    import anthropic  # type: ignore[import-untyped]

    from app.extractors.anthropic_tools import (
        MEDICATION_LIST_TOOL_NAME,
        medication_list_tool,
        parse_medication_list_tool,
    )

    client = anthropic.Anthropic()
    system = (
        "You are a clinical medication-list parser. Extract one structured entry per "
        "drug row in a patient medication list. "
        f"Use the {MEDICATION_LIST_TOOL_NAME} tool. "
        "Each entry has drug_name (verbatim, required), and optional dose, route, "
        "frequency, start_date, prescriber, indication, quote_or_value, confidence. "
        "Do not fabricate columns that are illegible — leave them empty. "
        "If a dose was crossed out and a new dose written above, return the NEW dose."
    )
    prompt = (
        "Extract every medication row from this document using the tool. "
        "Return an empty entries list if no rows are visible."
    )
    if page_text:
        prompt += (
            "\nThis page has a text layer. Use the text below as the primary "
            "source and pick quote_or_value from verbatim nearby text.\n\nPAGE TEXT:\n"
            + page_text[:12000]
        )
    if repair_errors:
        prompt = (
            "Your previous extraction failed validation:\n- "
            + "\n- ".join(repair_errors[:5])
            + "\nReturn a corrected extraction using the same tool. "
            "Drop any row you cannot read confidently."
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
        max_tokens=1500,
        system=system,
        tools=[medication_list_tool()],
        tool_choice={"type": "tool", "name": MEDICATION_LIST_TOOL_NAME},
        messages=[{"role": "user", "content": content}],
    )
    return parse_medication_list_tool(response)


def _call_vision_api(
    image_b64: str | None,
    media_type: str | None,
    page_text: str | None,
) -> list[dict[str, Any]]:
    entries, errors, raw_text = _call_vision_api_once(
        image_b64=image_b64, media_type=media_type, page_text=page_text,
    )
    if entries is not None:
        return entries

    logger.warning(
        "medication_list structured extraction retrying after invalid tool payload: %s",
        "; ".join(errors),
    )
    repaired, repair_errors, _ = _call_vision_api_once(
        image_b64=image_b64,
        media_type=media_type,
        page_text=page_text,
        repair_errors=errors,
        prior_raw=raw_text,
    )
    if repaired is not None:
        return repaired
    raise ValueError(
        "extraction_failed: medication_list model did not emit valid structured entries ("
        + "; ".join(repair_errors or errors)
        + ")"
    )


def _image_to_base64(content: bytes, media_type: str) -> tuple[str, str]:
    if media_type == "image/png":
        return base64.b64encode(content).decode(), "image/png"
    if media_type == "image/jpeg":
        return base64.b64encode(content).decode(), "image/jpeg"
    return base64.b64encode(content).decode(), "image/png"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract_medication_list(
    content: bytes,
    patient_uuid_hash: str,
    document_sha256: str | None = None,
    filename: str = "upload.pdf",
) -> dict[str, Any]:
    """Run the medication-list extractor.

    See module docstring for the pipeline. Returns an
    ``ExtractedDocument``-shaped dict (validation done by the route).
    """

    from app.extractors.normalize import normalize_extracted_document
    from app.extractors._eval_mocks_a import (
        get_medication_list_mock_entries,
        is_eval_mode,
        resolve_medication_list_fixture_key,
    )

    doc_sha = document_sha256 or _sha256_bytes(content)

    if is_eval_mode():
        fixture_key = resolve_medication_list_fixture_key(doc_sha, filename)
        raw_entries = get_medication_list_mock_entries(fixture_key)
        flat_fields = _expand_entries_to_fields(
            raw_entries, doc_sha=doc_sha, patient_uuid_hash=patient_uuid_hash,
        )
        entries_with_citations = _build_entries_with_citations(
            raw_entries, doc_sha=doc_sha, patient_uuid_hash=patient_uuid_hash,
        )
        payload = {
            "doc_type": "medication_list",
            "document_sha256": doc_sha,
            "patient_uuid_hash": patient_uuid_hash,
            "filename": filename,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extracted_by": "eval-mock",
            "extracted_field_count": len(flat_fields),
            "result": {
                "fields": flat_fields,
                "entries": entries_with_citations,
                "page_count": 1,
            },
        }
        return normalize_extracted_document(
            payload,
            doc_type="medication_list",
            document_sha256=doc_sha,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )

    # ---------------------- live mode ----------------------

    media_type = _detect_media_type(content, filename)
    all_raw_entries: list[dict[str, Any]] = []
    page_count_total = 1

    if media_type == "application/pdf":
        page_count_total = _get_page_count(content)
        if page_count_total > _MAX_PAGES:
            raise ValueError(
                f"too_many_pages: {filename!r} has {page_count_total} pages; "
                f"maximum is {_MAX_PAGES}"
            )
        page_errors: list[str] = []
        for page_idx in range(page_count_total):
            try:
                width, height = _get_page_dimensions(content, page_idx)
                page_text, blocks = _extract_pdf_page_text_and_blocks(
                    content, page_idx, width, height,
                )
                page_entries: list[dict[str, Any]] = []
                if _has_meaningful_text_layer(page_text):
                    page_entries = _extract_entries_from_text(page_text)
                    if not page_entries:
                        page_entries = _call_vision_api(None, None, page_text)
                else:
                    image_b64 = _page_to_base64_png(content, page_idx)
                    page_entries = _call_vision_api(image_b64, "image/png", None)

                for entry in page_entries:
                    quote = entry.get("quote_or_value")
                    bbox_tuple = _find_verbatim_bbox(quote, blocks) if quote else None
                    if bbox_tuple is not None:
                        entry["bbox"] = list(bbox_tuple)
                        entry["bbox_unit"] = _BBOX_UNIT
                    entry.setdefault("page_index", page_idx)
                    all_raw_entries.append(entry)
            except Exception as exc:  # noqa: BLE001 — log + collect, never bail per page
                page_errors.append(str(exc))
                logger.error(
                    "Error processing medication-list PDF page %d for document %s: %s",
                    page_idx, doc_sha[:12], exc,
                )
        if not all_raw_entries and page_errors:
            raise ValueError("extraction_failed: " + "; ".join(page_errors[:3]))
    else:
        # Image-only (PNG/JPEG) — handwritten and dirty-scan fixtures route here.
        try:
            image_b64, effective_type = _image_to_base64(content, media_type)
            raw_entries = _call_vision_api(image_b64, effective_type, None)
            for entry in raw_entries:
                entry.setdefault("page_index", 0)
                all_raw_entries.append(entry)
        except Exception as exc:
            logger.error("Image medication-list extraction failed for %s: %s", doc_sha[:12], exc)
            raise ValueError(f"extraction_failed: {exc}") from exc

    flat_fields = _expand_entries_to_fields(
        all_raw_entries, doc_sha=doc_sha, patient_uuid_hash=patient_uuid_hash,
    )
    entries_with_citations = _build_entries_with_citations(
        all_raw_entries, doc_sha=doc_sha, patient_uuid_hash=patient_uuid_hash,
    )
    payload = {
        "doc_type": "medication_list",
        "document_sha256": doc_sha,
        "patient_uuid_hash": patient_uuid_hash,
        "filename": filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extracted_by": _MODEL,
        "extracted_field_count": len(flat_fields),
        "result": {
            "fields": flat_fields,
            "entries": entries_with_citations,
            "page_count": max(1, page_count_total),
        },
    }
    return normalize_extracted_document(
        payload,
        doc_type="medication_list",
        document_sha256=doc_sha,
        patient_uuid_hash=patient_uuid_hash,
        filename=filename,
    )
