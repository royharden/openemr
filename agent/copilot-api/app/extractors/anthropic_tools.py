"""Shared Anthropic tool-use helpers for live document extraction."""

from __future__ import annotations

import json
from typing import Any

EXTRACT_FIELDS_TOOL_NAME = "emit_extracted_fields"

# AgDR-0077 / Plan §6.3 — medication-list extractor tool schema. The
# medication list needs a row-shaped tool input (drug_name + dose + route +
# frequency + start_date + prescriber + indication + quote) rather than the
# generic name+value pair used by lab and intake. Sharing the existing
# `emit_extracted_fields` tool would force the model to encode rows as
# heterogeneous `name=...` fields, which made the repair pass thrash.
MEDICATION_LIST_TOOL_NAME = "emit_medication_list_entries"


def extraction_fields_tool() -> dict[str, Any]:
    """Return the forced tool schema used by lab and intake extractors."""

    field_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "name": {
                "type": "string",
                "description": "Stable field path, such as ldl, vitals.blood_pressure, or medications.self_reported.",
            },
            "value": {
                "type": "string",
                "description": "The extracted field value as a string exactly as supported by the document.",
            },
            "unit": {"type": "string"},
            "abnormal": {"type": "boolean"},
            "flag": {"type": "string"},
            "reference_range": {"type": "string"},
            "loinc_code": {"type": "string"},
            "quote_or_value": {
                "type": "string",
                "description": "Verbatim supporting text from the document when available.",
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["name"],
    }
    return {
        "name": EXTRACT_FIELDS_TOOL_NAME,
        "description": "Emit structured document fields. Return only fields that are visibly present.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "fields": {
                    "type": "array",
                    "items": field_schema,
                    "maxItems": 80,
                    "description": "List of extracted fields. Use an empty list only if no clinical fields are visible.",
                }
            },
            "required": ["fields"],
        },
    }


def medication_list_tool() -> dict[str, Any]:
    """Return the forced tool schema for medication-list extraction (AgDR-0077).

    Each entry is one row of the source medication list. Only ``drug_name`` is
    required — every other column may be empty/illegible (handwritten and
    dirty-scan fixtures routinely drop frequency or start_date). The
    ``quote_or_value`` field is still encouraged so the downstream verifier
    can pin each entry to verbatim source text where one exists.
    """

    entry_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "drug_name": {
                "type": "string",
                "description": "Verbatim drug name as printed (generic or brand, whichever is on the form).",
            },
            "dose": {"type": "string", "description": "Dose with units, e.g. '500 mg'."},
            "route": {"type": "string", "description": "Route of administration, e.g. 'PO', 'INH', 'IM'."},
            "frequency": {"type": "string", "description": "Dosing frequency, e.g. 'BID', 'Daily', 'PRN'."},
            "start_date": {"type": "string", "description": "Start date — ISO 'YYYY-MM-DD' when known, fuzzy ('~2019') or 'unknown' when not."},
            "prescriber": {"type": "string", "description": "Prescriber name as printed, e.g. 'Patel, N.' or 'Home PCP'."},
            "indication": {"type": "string", "description": "Indication / diagnosis as printed."},
            "quote_or_value": {
                "type": "string",
                "description": "Verbatim source-row text from the document, when available.",
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["drug_name"],
    }
    return {
        "name": MEDICATION_LIST_TOOL_NAME,
        "description": "Emit one entry per drug row in the medication list. Use empty/null fields for columns that are illegible or missing.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entries": {
                    "type": "array",
                    "items": entry_schema,
                    "maxItems": 40,
                    "description": "List of medication-list rows. Use [] if no rows are visible.",
                },
            },
            "required": ["entries"],
        },
    }


def parse_medication_list_tool(response: Any) -> tuple[list[dict[str, Any]] | None, list[str], str]:
    """Return ``(entries, errors, raw_text)`` from an Anthropic tool response.

    ``entries is None`` means the model did not emit a valid
    ``emit_medication_list_entries`` tool call. ``entries == []`` is a valid
    extraction — the model asserts no rows were visible.
    """

    raw_text = ""
    tool_input: dict[str, Any] | None = None
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            raw_text += str(getattr(block, "text", ""))
        elif block_type == "tool_use" and getattr(block, "name", None) == MEDICATION_LIST_TOOL_NAME:
            candidate = getattr(block, "input", None)
            if isinstance(candidate, dict):
                tool_input = candidate

    if tool_input is None:
        return None, ["missing emit_medication_list_entries tool call"], raw_text

    entries_raw = tool_input.get("entries")
    if not isinstance(entries_raw, list):
        return None, ["tool input.entries must be an array"], raw_text

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, entry in enumerate(entries_raw):
        if not isinstance(entry, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        drug_name = str(entry.get("drug_name") or entry.get("name") or "").strip()
        if not drug_name:
            errors.append(f"entries[{index}].drug_name is required")
            continue
        next_entry = dict(entry)
        next_entry["drug_name"] = drug_name
        normalized.append(next_entry)

    if errors:
        return None, errors, raw_text
    return normalized, [], raw_text


def _find_field_list(value: Any) -> list[Any] | None:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        if any(
            any(alias in item for alias in ("name", "field_name", "test_name", "label"))
            for item in value
        ):
            return value
    if isinstance(value, dict):
        for key in ("fields", "extracted_fields", "lab_results", "intake_fields", "results", "items"):
            found = _find_field_list(value.get(key))
            if found is not None:
                return found
        for nested in value.values():
            found = _find_field_list(nested)
            if found is not None:
                return found
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                return _find_field_list(json.loads(stripped))
            except json.JSONDecodeError:
                return None
    return None


def _dict_to_field_list(value: dict[str, Any]) -> list[dict[str, Any]] | None:
    metadata_keys = {
        "fields",
        "extracted_fields",
        "lab_results",
        "intake_fields",
        "results",
        "items",
        "patient",
        "patient_name",
        "document",
        "document_type",
        "page",
        "page_number",
        "confidence",
    }
    field_like: list[dict[str, Any]] = []
    for key, item in value.items():
        if key in metadata_keys:
            continue
        if isinstance(item, dict):
            next_item = dict(item)
            next_item.setdefault("name", key)
            field_like.append(next_item)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            field_like.append({"name": key, "value": item, "quote_or_value": None if item is None else str(item)})
    return field_like or None


def parse_extracted_fields_tool(response: Any) -> tuple[list[dict[str, Any]] | None, list[str], str]:
    """Return ``(fields, errors, raw_text)`` from an Anthropic tool response.

    ``fields is None`` means the model did not call the expected tool or
    emitted a schema-invalid payload. ``fields == []`` is a valid extraction
    result: the model called the tool and asserted that no supported fields
    were visible.
    """

    raw_text = ""
    tool_input: dict[str, Any] | None = None
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            raw_text += str(getattr(block, "text", ""))
        elif block_type == "tool_use" and getattr(block, "name", None) == EXTRACT_FIELDS_TOOL_NAME:
            candidate = getattr(block, "input", None)
            if isinstance(candidate, dict):
                tool_input = candidate

    if tool_input is None:
        return None, ["missing emit_extracted_fields tool call"], raw_text

    fields = _find_field_list(tool_input)
    if not isinstance(fields, list) and isinstance(tool_input.get("fields"), dict):
        fields = _dict_to_field_list(tool_input["fields"])
    if not isinstance(fields, list) and any(alias in tool_input for alias in ("name", "field_name", "test_name", "label")):
        fields = [tool_input]
    if not isinstance(fields, list):
        fields = _dict_to_field_list(tool_input)
    if not isinstance(fields, list):
        keys = ", ".join(sorted(map(str, tool_input.keys())))[:160]
        return None, [f"tool input must contain field objects; keys=[{keys}]"], raw_text

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            errors.append(f"fields[{index}] must be an object")
            continue
        name = str(
            field.get("name")
            or field.get("field_name")
            or field.get("test_name")
            or field.get("label")
            or ""
        ).strip()
        if not name:
            errors.append(f"fields[{index}].name is required")
            continue
        next_field = dict(field)
        next_field["name"] = name
        if "value" not in next_field:
            for value_key in ("result_value", "field_value", "result", "answer"):
                if value_key in next_field:
                    next_field["value"] = next_field[value_key]
                    break
        if "quote_or_value" not in next_field:
            for quote_key in ("quote", "source_quote", "evidence", "verbatim"):
                if quote_key in next_field:
                    next_field["quote_or_value"] = next_field[quote_key]
                    break
        if "abnormal" not in next_field:
            next_field["abnormal"] = False
        normalized.append(next_field)

    if errors:
        return None, errors, raw_text
    return normalized, [], raw_text
