"""Pydantic schemas — single source of truth for request/response shapes."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


SourceType = Literal["openemr_packet", "document_extract", "guideline_chunk"]
BboxUnit = Literal["exact", "approximate"]


class SourcePacket(BaseModel):
    """Source-of-truth packet for one extracted fact.

    Wk1 packets carry only the OpenEMR-native fields (source_id, patient_uuid,
    resource_type, source_table, field, label, value, unit, observed_at,
    freshness, status, sensitive).

    Wk2 (Plan §3 #13, §12 Citation Contract) extends the same model with
    optional fields used by document_extract and guideline_chunk packets.
    All Wk2 additions are optional with default None so Wk1 packets keep
    validating unchanged.
    """

    source_id: str
    patient_uuid: str
    resource_type: str
    source_table: str
    source_uuid: str | None = None
    field: str
    label: str
    value: Any = None
    unit: str | None = None
    observed_at: str | None = None
    last_updated: str | None = None
    freshness: Literal["recent", "stale", "unknown"] = "unknown"
    status: str | None = None
    sensitive: bool = False

    # --- Wk2 citation-contract extension (Plan §3 #13, §12, AgDR-0039) ---
    # All optional. Required combinations enforced by verifier rules
    # (bbox_well_formed, quote_verbatim_in_pdf, chunk_id_in_corpus,
    # extracted_field_in_schema, guideline_grade_present), not Pydantic.
    source_type: SourceType | None = None
    page_or_section: str | None = None
    field_or_chunk_id: str | None = None
    quote_or_value: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    bbox_unit: BboxUnit | None = None
    confidence: float | None = None
    page_index: int | None = None
    recommendation_grade: str | None = None  # ACIP A|B, USPSTF A|B|C|D|I, etc.
    source_year: int | None = None
    source_organization: str | None = None  # CDC-ACIP | FDA | HMS-LOE | ...

    @field_validator("bbox")
    @classmethod
    def _bbox_in_unit_range(
        cls, v: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        if v is None:
            return v
        x0, y0, x1, y1 = v
        for c in v:
            if not 0.0 <= c <= 1.0:
                raise ValueError("bbox coordinates must be in [0, 1] (normalized fractions)")
        if not (x0 < x1 and y0 < y1):
            raise ValueError("bbox must satisfy x0<x1 and y0<y1")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_in_unit_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        return v


UseCase = Literal[
    "pre_room_brief",
    "what-changed",
    "medication_check",
    "allergy_check",
    "recent_abnormal_labs",
    "immunization_history",
    "free_text_followup",
]

ClinicalToolName = Literal[
    "get_patient_identity",
    "get_active_problems",
    "get_active_medications",
    "get_allergy_list",
    "get_recent_labs",
    "get_immunization_history",
    # Wk2 (Plan §3 #21, §6 Workstream A) — gateway-allowlisted document tool.
    # Body implemented by Team A; literal locked here so Team C can write
    # graph routing logic without merge-collision risk.
    "attach_and_extract",
]

PlannerStatus = Literal["planned", "fallback_required", "failed"]


class ToolCall(BaseModel):
    name: ClinicalToolName
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def _reject_patient_or_query_args(cls, v: dict[str, Any]) -> dict[str, Any]:
        forbidden = {
            "pid",
            "patient_id",
            "patient_uuid",
            "patient_uuid_hash",
            "sql",
            "query",
            "table",
            "table_name",
            "source_id",
        }
        bad = forbidden.intersection(v.keys())
        if bad:
            raise ValueError(f"forbidden tool argument(s): {', '.join(sorted(bad))}")
        return v


class ToolPlanRequest(BaseModel):
    trace_id: str
    use_case: UseCase = "pre_room_brief"
    patient_uuid_hash: str = Field(..., description="SHA256-truncated patient UUID")
    question: str | None = Field(None, max_length=500)
    router_family: str | None = Field(None, max_length=64)

    @field_validator("question")
    @classmethod
    def _no_control_chars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _CONTROL_CHAR_RE.search(v):
            raise ValueError("question contains control characters")
        return v


class ToolPlanResponse(BaseModel):
    trace_id: str
    planner_status: PlannerStatus
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=6)
    usage: dict[str, Any] = Field(default_factory=dict)


class BriefRequest(BaseModel):
    trace_id: str
    use_case: UseCase = "pre_room_brief"
    patient_uuid_hash: str = Field(..., description="SHA256-truncated patient UUID")
    packets: list[SourcePacket]
    question: str | None = Field(
        None,
        max_length=500,
        description="Free-text question for the free_text_followup use case. Gateway "
        "must normalize and strip control chars before sending.",
    )
    prior_turn_source_ids: list[str] | None = Field(
        None,
        max_length=20,
        description="Verified source_ids from the prior turn (display-only context, IDs only).",
    )
    router_family: str | None = Field(
        None,
        max_length=64,
        description="Gateway-classified family for free-text questions, used as observability metadata.",
    )
    selected_tools: list[ClinicalToolName] | None = Field(
        None,
        max_length=6,
        description="Gateway-executed tool names selected by the sidecar planner or fallback map.",
    )
    planner_status: PlannerStatus | None = Field(
        None,
        description="How the gateway obtained the selected tool list.",
    )
    tool_results_summary: list[dict[str, Any]] | None = Field(
        None,
        max_length=6,
        description="PHI-minimized per-tool packet counts and execution status.",
    )

    @field_validator("question")
    @classmethod
    def _no_control_chars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _CONTROL_CHAR_RE.search(v):
            raise ValueError("question contains control characters")
        return v


class Claim(BaseModel):
    text: str = Field(..., description="Rendered to physician verbatim. Plain text only.")
    claim_type: Literal["fact", "trend", "absence", "conflict"]
    source_ids: list[str] = Field(
        ...,
        description="Each ID MUST exist in the request packet set. Empty list = unsupported.",
    )
    caveat: str | None = None


class LLMOutput(BaseModel):
    answer_type: Literal["pre_room_brief", "follow_up", "refusal"]
    claims: list[Claim] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    refusals: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    trace_id: str
    verdict: Literal[
        "helpful",
        "missing_data",
        "incorrect",
        "too_slow",
        "source_unclear",
    ]
    comment: str = ""


class FeedbackAck(BaseModel):
    trace_id: str
    verdict: str
    recorded: bool


class LocalRefusalRequest(BaseModel):
    trace_id: str
    use_case: str = Field(..., max_length=64)
    router_family: str = Field(..., max_length=64)
    refusal_reason: str = Field(..., max_length=128)
    patient_uuid_hash: str = Field(..., max_length=64)


class LocalRefusalAck(BaseModel):
    trace_id: str
    recorded: bool


class VerifierIssue(BaseModel):
    rule: str
    claim_index: int | None = None
    detail: str


# AgDR-0075 — Critic LLM worker output (Phase 6.1). The critic runs between
# synthesizer and verifier and emits a per-claim verdict the UI consumes to
# render an amber "uncertain" indicator (warn) or a hard safe-refusal (reject).
CriticSeverity = Literal["warn", "reject"]


class CriticFlag(BaseModel):
    """One flagged claim from the critic LLM worker."""

    claim_index: int = Field(..., ge=0, description="Zero-based index into LLMOutput.claims")
    reason: str = Field(..., max_length=400)
    severity: CriticSeverity


class CriticVerdict(BaseModel):
    """Critic worker verdict over a synthesized brief (AgDR-0075).

    ``accepted=False`` with at least one ``severity="reject"`` flag forces a
    safe refusal upstream of the verifier. ``accepted=True`` with no flags is
    the happy path. A mix of ``warn`` flags is non-fatal: the brief passes
    through but per-claim metadata is preserved so the UI can render
    "uncertain" chips.
    """

    accepted: bool
    flagged_claims: list[CriticFlag] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class VerifiedResponse(BaseModel):
    answer_type: str
    claims: list[Claim]
    missing_data: list[str]
    refusals: list[str]
    suggested_followups: list[str]
    verifier_status: Literal["passed", "passed_with_drops", "failed"]
    unsupported_dropped: int = 0
    verifier_issues: list[VerifierIssue] = Field(default_factory=list)
    trace_id: str
    selected_tools: list[ClinicalToolName] = Field(default_factory=list)
    planner_status: PlannerStatus | None = None
    tool_results_summary: list[dict[str, Any]] = Field(default_factory=list)
    # AgDR-0075 — propagates the critic's per-claim verdict so the UI can
    # render an amber "uncertain" chip for warn-only flags and the audit
    # surface can log critic rejections. Optional with default None so
    # pre-AgDR-0075 callers keep validating unchanged.
    critic_verdict: CriticVerdict | None = None


# ---------------------------------------------------------------------------
# Wk2 Workstream 0.5 — contract-freeze shells for extraction pipeline
# (Plan §5 step 7, §6 Workstream A, §15 Team A brief)
#
# Team A extends the bodies (extractor logic, exact field set per doc type).
# Field NAMES at the envelope level are locked here so Team A and Team C can
# work in parallel without renaming risk. Inner field collections stay
# permissive — the value list is keyed by `name` so Team A can grow it without
# changing the envelope shape.
# ---------------------------------------------------------------------------

DocumentType = Literal["lab_pdf", "intake_form", "medication_list"]


class ExtractedField(BaseModel):
    """One field pulled from a document, with its citation packet.

    Locked envelope (W0.5):
      - name       (string field path, e.g. ``vitals.bp_systolic`` or ``ldl``)
      - value      (string|number|null — coerced to string in storage layer)
      - unit       (optional unit string, e.g. ``mg/dL``)
      - reference_range (optional, e.g. ``<100``)
      - flag       (optional H/L/N/A flag)
      - loinc_code (optional, populated when extractor recognizes a code)
      - citation   (REQUIRED for non-null value — the SourcePacket that
                    proves where this came from)
    """

    name: str = Field(..., max_length=128)
    value: str | float | int | bool | None = None
    unit: str | None = Field(None, max_length=32)
    reference_range: str | None = Field(None, max_length=64)
    flag: str | None = Field(None, max_length=8)
    loinc_code: str | None = Field(None, max_length=32)
    citation: SourcePacket | None = None


class LabResult(BaseModel):
    """Strict schema for a lab PDF extraction (Plan §6 Workstream A).

    Envelope locked at W0.5 contract-freeze; inner field set is dynamic.
    Extractor implementation (vision + pdfplumber bbox) lives at
    ``app.extractors.lab_pdf`` (Team A).
    """

    document_sha256: str = Field(..., min_length=64, max_length=64)
    page_count: int = Field(..., ge=1)
    extracted_at: str  # ISO 8601 UTC
    extracted_by_model: str = Field(..., max_length=64)
    fields: list[ExtractedField] = Field(default_factory=list)


class IntakeFields(BaseModel):
    """Strict schema for an intake-form extraction (Plan §6 Workstream A)."""

    document_sha256: str = Field(..., min_length=64, max_length=64)
    page_count: int = Field(..., ge=1)
    extracted_at: str  # ISO 8601 UTC
    extracted_by_model: str = Field(..., max_length=64)
    fields: list[ExtractedField] = Field(default_factory=list)


class MedicationListEntry(BaseModel):
    """One medication row extracted from a patient medication list (Plan §6.3).

    AgDR-0077 — the medication-list doc type adds a third extraction surface
    (alongside lab_pdf and intake_form). Each entry mirrors the OpenEMR
    `prescriptions` table's column shape (drug / dose / route / frequency /
    start_date / prescriber / indication) so the downstream reconciliation
    panel (``MedicationReconciliation``) can string-match against the seed
    prescriptions data without a translation layer.

    ``source_citation`` is REQUIRED: every entry must carry a SourcePacket
    proving where it came from. Per AgDR-0040 the bbox may be ``None``
    (handwritten PNG) but the packet itself is non-optional — an entry
    without a citation cannot survive verifier_rule.citation_present.
    """

    drug_name: str = Field(..., max_length=128)
    dose: str | None = Field(None, max_length=64)
    route: str | None = Field(None, max_length=32)
    frequency: str | None = Field(None, max_length=64)
    start_date: str | None = Field(None, max_length=32)  # YYYY-MM-DD or fuzzy ("~2019", "unknown")
    prescriber: str | None = Field(None, max_length=128)
    indication: str | None = Field(None, max_length=256)
    source_citation: SourcePacket


class ExtractedMedicationList(BaseModel):
    """Strict schema for a medication-list extraction (Plan §6.3, AgDR-0077).

    Envelope follows the same shape as ``LabResult`` and ``IntakeFields`` so
    the gateway's ``DocumentFactsRepository`` can persist entries through
    the existing ``ExtractedField``-based path. Per-entry data lives in
    ``entries`` (the MedicationListEntry list), while ``fields`` keeps the
    flat-field surface non-empty for downstream consumers (each entry is
    re-emitted as a ``medication.<drug>.<attr>`` field path so the
    citation-present rubric and the document-facts table see the same row
    shape they see for lab/intake extractions).
    """

    document_sha256: str = Field(..., min_length=64, max_length=64)
    page_count: int = Field(..., ge=1)
    extracted_at: str  # ISO 8601 UTC
    extracted_by_model: str = Field(..., max_length=64)
    fields: list[ExtractedField] = Field(default_factory=list)
    entries: list[MedicationListEntry] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    """Sidecar response envelope for ``POST /v1/extract/{lab-pdf,intake-form}``.

    PHP gateway is the only writer to ``copilot_document_facts``. The sidecar
    returns this structure; the gateway calls
    ``DocumentFactsRepository`` to persist the fields with the
    SHA-256(patient_uuid + document_sha256 + field_path) idempotency key.
    """

    doc_type: DocumentType
    document_sha256: str = Field(..., min_length=64, max_length=64)
    result: LabResult | IntakeFields | ExtractedMedicationList
    source_packets: list[SourcePacket] = Field(default_factory=list)
    extracted_field_count: int = 0
    dropped_field_count: int = 0  # claims dropped by quote_verbatim_in_pdf etc.
