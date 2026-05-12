"""Unit coverage for live Anthropic tool-use contracts (Phase 5.1)."""

from __future__ import annotations

import hashlib
from typing import Any


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _ToolBlock:
    type = "tool_use"

    def __init__(self, name: str, input_payload: dict[str, Any]) -> None:
        self.name = name
        self.input = input_payload


class _Response:
    def __init__(self, blocks: list[Any]) -> None:
        self.content = blocks


class _FakeMessages:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake Anthropic response queued")
        return self.responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list[_Response]) -> None:
        self.messages = _FakeMessages(responses)


def _patch_anthropic(monkeypatch: Any, client: _FakeClient) -> None:
    monkeypatch.setattr("anthropic.Anthropic", lambda *args, **kwargs: client)


def test_lab_extractor_parses_forced_tool_use(monkeypatch: Any) -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME
    from app.extractors.lab_pdf import _call_vision_api

    client = _FakeClient([
        _Response([
            _TextBlock("ignored prose"),
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "fields": [
                        {
                            "name": "ldl",
                            "value": 158,
                            "unit": "mg/dL",
                            "abnormal": True,
                            "quote_or_value": "LDL 158 mg/dL",
                            "confidence": 0.98,
                        }
                    ]
                },
            ),
        ])
    ])
    _patch_anthropic(monkeypatch, client)

    fields = _call_vision_api("base64-image", "patient-hash")

    assert fields[0]["name"] == "ldl"
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": EXTRACT_FIELDS_TOOL_NAME}
    assert call["tools"][0]["name"] == EXTRACT_FIELDS_TOOL_NAME


def test_extractor_tool_parser_accepts_common_field_list_alias() -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME, parse_extracted_fields_tool

    fields, errors, _ = parse_extracted_fields_tool(
        _Response([
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "lab_results": [
                        {
                            "name": "hdl",
                            "value": 48,
                            "quote_or_value": "HDL 48 mg/dL",
                        }
                    ]
                },
            )
        ])
    )

    assert errors == []
    assert fields is not None
    assert fields[0]["name"] == "hdl"


def test_extractor_tool_parser_recovers_nested_field_aliases() -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME, parse_extracted_fields_tool

    fields, errors, _ = parse_extracted_fields_tool(
        _Response([
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "document": {
                        "results": [
                            {
                                "test_name": "LDL",
                                "result_value": "158",
                                "unit": "mg/dL",
                                "quote": "LDL 158 mg/dL",
                            }
                        ]
                    }
                },
            )
        ])
    )

    assert errors == []
    assert fields is not None
    assert fields[0]["name"] == "LDL"
    assert fields[0]["value"] == "158"
    assert fields[0]["quote_or_value"] == "LDL 158 mg/dL"


def test_extractor_tool_parser_recovers_mapping_payload() -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME, parse_extracted_fields_tool

    fields, errors, _ = parse_extracted_fields_tool(
        _Response([
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "ldl": {
                        "value": 158,
                        "unit": "mg/dL",
                        "quote_or_value": "LDL 158 mg/dL",
                    }
                },
            )
        ])
    )

    assert errors == []
    assert fields is not None
    assert fields[0]["name"] == "ldl"
    assert fields[0]["value"] == 158


def test_extractor_tool_parser_recovers_fields_object_mapping() -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME, parse_extracted_fields_tool

    fields, errors, _ = parse_extracted_fields_tool(
        _Response([
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "fields": {
                        "total_cholesterol": {
                            "value": "232",
                            "unit": "mg/dL",
                            "quote_or_value": "Total Cholesterol 232 mg/dL",
                        }
                    }
                },
            )
        ])
    )

    assert errors == []
    assert fields is not None
    assert fields[0]["name"] == "total_cholesterol"


def test_intake_extractor_retries_missing_tool_call(monkeypatch: Any) -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME
    from app.extractors.intake_form import _call_vision_api_intake

    client = _FakeClient([
        _Response([_TextBlock("[{\"name\": \"bad raw json\"")]),
        _Response([
            _ToolBlock(
                EXTRACT_FIELDS_TOOL_NAME,
                {
                    "fields": [
                        {
                            "name": "demographics.first_name",
                            "value": "Elena",
                            "quote_or_value": None,
                            "confidence": 0.87,
                        }
                    ]
                },
            )
        ]),
    ])
    _patch_anthropic(monkeypatch, client)

    fields = _call_vision_api_intake("base64-image", "image/png", "patient-hash")

    assert fields == [
        {
            "name": "demographics.first_name",
            "value": "Elena",
            "quote_or_value": None,
            "confidence": 0.87,
            "abnormal": False,
        }
    ]
    assert len(client.messages.calls) == 2
    assert "failed validation" in client.messages.calls[1]["messages"][0]["content"][1]["text"]


def test_image_intake_falls_back_to_key_value_lines(monkeypatch: Any) -> None:
    from app.extractors.anthropic_tools import EXTRACT_FIELDS_TOOL_NAME
    from app.extractors.intake_form import _call_vision_api_intake

    client = _FakeClient([
        _Response([_ToolBlock(EXTRACT_FIELDS_TOOL_NAME, {})]),
        _Response([_ToolBlock(EXTRACT_FIELDS_TOOL_NAME, {"fields": {}})]),
        _Response([
            _TextBlock(
                "\n".join(
                    [
                        "demographics.first_name=Sofia",
                        "demographics.last_name=Reyes",
                        "demographics.date_of_birth=12/19/1983",
                        "chief_complaint=blurry vision",
                    ]
                )
            )
        ]),
    ])
    _patch_anthropic(monkeypatch, client)

    fields = _call_vision_api_intake("base64-image", "image/png", "patient-hash")

    by_name = {field["name"]: field["value"] for field in fields}
    assert by_name["demographics.first_name"] == "Sofia"
    assert by_name["demographics.last_name"] == "Reyes"
    assert by_name["chief_complaint"] == "blurry vision"
    assert len(client.messages.calls) == 3


def test_typed_pdf_intake_uses_text_layer_before_rendering(monkeypatch: Any) -> None:
    import app.extractors._eval_mocks_a as mocks
    import app.extractors.intake_form as intake

    original_eval_mode = mocks._EVAL_MODE
    mocks._EVAL_MODE = False
    patient_hash = hashlib.sha256(b"patient").hexdigest()
    text = "Chief concern Annual physical exam Review of systems typed page with enough words for text mode"
    blocks = [
        {"text": "Annual", "x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.15},
        {"text": "physical", "x0": 0.21, "y0": 0.1, "x1": 0.3, "y1": 0.15},
        {"text": "exam", "x0": 0.31, "y0": 0.1, "x1": 0.38, "y1": 0.15},
    ]

    try:
        monkeypatch.setattr(intake, "_get_page_count_pdf", lambda _content: 1)
        monkeypatch.setattr(intake, "_extract_pdf_page_text_and_blocks", lambda _content, _page: (text, blocks))
        monkeypatch.setattr(
            intake,
            "_pdf_page_to_base64_png",
            lambda *_args: (_ for _ in ()).throw(AssertionError("typed PDF should not render image")),
        )

        def fake_tool_api(**kwargs: Any) -> list[dict[str, Any]]:
            assert kwargs["image_b64"] is None
            assert kwargs["page_text"] == text
            return [
                {
                    "name": "chief_complaint",
                    "value": "Annual physical exam",
                    "quote_or_value": "Annual physical exam",
                    "confidence": 0.96,
                }
            ]

        monkeypatch.setattr(intake, "_call_structured_intake_api", fake_tool_api)
        result = intake.extract_intake_form(
            b"%PDF-1.4 typed",
            patient_hash,
            document_sha256="c" * 64,
            filename="typed.pdf",
        )
    finally:
        mocks._EVAL_MODE = original_eval_mode

    field = result["result"]["fields"][0]
    assert field["name"] == "chief_complaint"
    assert field["bbox"] == [0.1, 0.1, 0.38, 0.15]


def test_typed_pdf_intake_text_fallback_recovers_demographics() -> None:
    from app.extractors.intake_form import _extract_intake_fields_from_text

    fields = _extract_intake_fields_from_text(
        "\n".join(
            [
                "LEGAL NAME Chen, DATE OF BIRTH 1967-08-14",
                "Margaret L.",
                "SEX ASSIGNED AT BIRTH Female GENDER IDENTITY Female",
                "HOME ADDRESS 4421 Magnolia Ave, Apt 3B, Berkeley, CA 94705",
                "MOBILE PHONE (510) 555- EMAIL mchen.demo@example.test",
                "0148",
                "CHIEF CONCERN Tired during the day",
                "ONSET / DURATION 3 weeks",
                "Lisinopril 10 mg PO daily (AM) 2018 314076 High blood pressure",
            ]
        )
    )

    by_name = {field["name"]: field["value"] for field in fields}
    assert by_name["demographics.first_name"] == "Margaret"
    assert by_name["demographics.last_name"] == "Chen"
    assert by_name["demographics.date_of_birth"] == "1967-08-14"
    assert by_name["demographics.phone"] == "(510) 555-0148"
    assert by_name["chief_complaint"] == "Tired during the day"


def test_lab_text_layer_fallback_recovers_table_rows() -> None:
    from app.extractors.lab_pdf import _extract_lab_fields_from_text

    fields = _extract_lab_fields_from_text(
        "\n".join(
            [
                "TEST RESULT FLAG REFERENCE RANGE UNITS",
                "Cholesterol, Total 232 H Desirable <200 mg/dL Enzymatic",
                "HDL Cholesterol 48 L Female >=50 mg/dL Direct",
                "LDL Cholesterol, 158 H Optimal <100 mg/dL Calculated",
                "Triglycerides 178 H Normal <150 mg/dL Enzymatic",
                "Non-HDL Cholesterol 184 H Goal <130 mg/dL Calculated",
            ]
        )
    )

    assert [field["name"] for field in fields] == [
        "total_cholesterol",
        "hdl",
        "ldl",
        "triglycerides",
        "non_hdl_cholesterol",
    ]
    assert fields[2]["value"] == "158"
    assert fields[2]["unit"] == "mg/dL"
    assert fields[2]["abnormal"] is True


def test_graph_synthesizer_uses_tool_use_after_repair(monkeypatch: Any) -> None:
    from app.graph.nodes import _call_synthesizer

    client = _FakeClient([
        _Response([_TextBlock("{not valid json")]),
        _Response([
            _ToolBlock(
                "emit_briefing",
                {
                    "answer_type": "follow_up",
                    "claims": [
                        {
                            "text": "LDL is available at 158 mg/dL.",
                            "claim_type": "fact",
                            "source_ids": ["lab-1"],
                            "caveat": None,
                        }
                    ],
                    "missing_data": [],
                    "refusals": [],
                    "suggested_followups": [],
                },
            )
        ]),
    ])
    _patch_anthropic(monkeypatch, client)

    result = _call_synthesizer({
        "question": "What is Chen's LDL?",
        "extracted_packets": [
            {
                "source_id": "lab-1",
                "label": "LDL",
                "value": "158 mg/dL",
            }
        ],
        "guideline_packets": [],
    })

    assert result["claims"][0]["source_ids"] == ["lab-1"]
    assert len(client.messages.calls) == 2
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "emit_briefing"}
