"""Document extractors — lab PDF and intake form (Workstream A)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .normalize import normalize_extracted_document


def run_extraction(
    documents: list[dict[str, str]],
    patient_uuid_hash: str,
) -> dict[str, Any]:
    """Run the appropriate extractor for each graph document reference."""

    extracted_documents: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []
    low_confidence_count = 0

    for document in documents:
        path_raw = document.get("path") or document.get("tmp_path") or ""
        if not path_raw:
            continue
        path = Path(path_raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        content = path.read_bytes()
        filename = document.get("filename") or path.name
        doc_sha = document.get("document_sha256") or hashlib.sha256(content).hexdigest()
        doc_type = document.get("doc_type") or ("intake_form" if filename.lower().endswith((".png", ".jpg", ".jpeg")) else "lab_pdf")

        if doc_type == "intake_form":
            from .intake_form import extract_intake_form

            raw = extract_intake_form(content, patient_uuid_hash, doc_sha, filename)
        else:
            from .lab_pdf import extract_lab_pdf

            raw = extract_lab_pdf(content, patient_uuid_hash, doc_sha, filename)
            doc_type = "lab_pdf"

        normalized = normalize_extracted_document(
            raw,
            doc_type=doc_type,
            document_sha256=doc_sha,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )
        extracted_documents.append(normalized)
        packets.extend(normalized.get("source_packets", []))
        for field in normalized.get("result", {}).get("fields", []):
            citation = field.get("citation") if isinstance(field, dict) else None
            if isinstance(citation, dict) and float(citation.get("confidence") or 1.0) < 0.70:
                low_confidence_count += 1

    return {
        "documents": extracted_documents,
        "packets": packets,
        "low_confidence_count": low_confidence_count,
    }


__all__ = ["run_extraction"]
