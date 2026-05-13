"""Normalize extractor payloads into the strict Week 2 contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_extracted_document(
    payload: dict[str, Any],
    *,
    doc_type: str,
    document_sha256: str,
    patient_uuid_hash: str,
    filename: str,
) -> dict[str, Any]:
    """Return an ExtractedDocument-shaped payload with per-field citations."""

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    raw_fields = result.get("fields") if isinstance(result, dict) else []
    fields = [f for f in raw_fields if isinstance(f, dict)]
    extracted_at = str(payload.get("extracted_at") or result.get("extracted_at") or datetime.now(timezone.utc).isoformat())
    extracted_by = str(payload.get("extracted_by") or result.get("extracted_by_model") or "unknown")
    page_count = int(result.get("page_count") or payload.get("page_count") or 1)

    normalized_fields: list[dict[str, Any]] = []
    source_packets: list[dict[str, Any]] = []
    if doc_type == "lab_pdf":
        prefix = "lab"
        resource_type = "Observation"
    elif doc_type == "medication_list":
        prefix = "medication"
        resource_type = "MedicationStatement"
    else:
        prefix = "intake"
        resource_type = "QuestionnaireResponse"

    for index, field in enumerate(fields):
        name = str(field.get("name") or "").strip()
        if not name:
            continue

        field_path = name if name.startswith(prefix + ".") else f"{prefix}.{name}"
        source_id = str(field.get("source_id") or f"doc:{document_sha256[:12]}:{field_path}:{index}")
        value = field.get("value")
        quote = field.get("quote_or_value")
        if quote is None and value is not None:
            quote = str(value)

        citation = {
            "source_id": source_id,
            "patient_uuid": patient_uuid_hash,
            "resource_type": resource_type,
            "source_table": "document_upload",
            "source_uuid": None,
            "field": field_path,
            "label": name.replace("_", " ").title(),
            "value": value,
            "unit": field.get("unit"),
            "observed_at": extracted_at,
            "last_updated": extracted_at,
            "freshness": "recent",
            "status": field.get("flag") or ("H" if field.get("abnormal") else None),
            "sensitive": False,
            "source_type": "document_extract",
            "field_or_chunk_id": field_path,
            "quote_or_value": quote,
            "bbox": field.get("bbox"),
            "bbox_unit": field.get("bbox_unit"),
            "confidence": field.get("confidence"),
            "page_index": field.get("page_index", 0),
            "page_or_section": field.get("page_or_section"),
        }
        citation = {k: v for k, v in citation.items() if v is not None}
        if "bbox" in field:
            citation["bbox"] = field.get("bbox")
        source_packets.append(citation)

        normalized_fields.append({
            "name": name,
            "value": value,
            "unit": field.get("unit"),
            "reference_range": field.get("reference_range"),
            "flag": field.get("flag") or ("H" if field.get("abnormal") else None),
            "loinc_code": field.get("loinc_code"),
            "citation": citation,
            "quote_or_value": quote,
            "page_index": field.get("page_index", 0),
            "bbox": field.get("bbox"),
            "bbox_unit": field.get("bbox_unit"),
            "confidence": field.get("confidence"),
        })

    result_payload: dict[str, Any] = {
        "document_sha256": document_sha256,
        "page_count": max(1, page_count),
        "extracted_at": extracted_at,
        "extracted_by_model": extracted_by,
        "fields": normalized_fields,
    }

    # AgDR-0077 — medication-list extractor carries a structured `entries`
    # list (one per drug row) alongside the flat `fields` surface. The
    # entries are passed through unchanged so the reconciliation panel can
    # read drug_name/dose/route/etc. without re-deriving them from the
    # field-path strings. Other doc types do not populate `entries`.
    raw_entries = result.get("entries") if isinstance(result, dict) else None
    if isinstance(raw_entries, list) and raw_entries:
        result_payload["entries"] = list(raw_entries)

    return {
        "doc_type": doc_type,
        "document_sha256": document_sha256,
        "patient_uuid_hash": patient_uuid_hash,
        "filename": filename,
        "result": result_payload,
        "source_packets": source_packets,
        "extracted_field_count": len(normalized_fields),
        "dropped_field_count": int(payload.get("dropped_field_count") or 0),
    }
