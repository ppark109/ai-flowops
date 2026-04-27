from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Route = Literal["auto_approve", "legal", "security", "implementation", "finance"]
Severity = Literal["low", "medium", "high", "critical"]
CaseStatus = Literal[
    "draft",
    "normalized",
    "analyzed",
    "routed",
    "awaiting_approval",
    "approved",
    "rejected",
    "completed",
]
ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "override_route",
    "request_info",
]
TaskStatus = Literal["open", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high"]


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise TypeError("metadata must be a mapping")


class DocumentRef(BaseModel):
    document_id: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    content_hash: str | None = None


class IntakePackage(BaseModel):
    case_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    account_name: str | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    intake_email_text: str = Field(min_length=1)
    contract_text: str = Field(min_length=1)
    order_form_text: str = Field(min_length=1)
    implementation_notes: str = Field(min_length=1)
    security_questionnaire_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)


class SeedCase(IntakePackage):
    expected_route: Route
    expected_approval_required: bool
    expected_key_risk_labels: list[str] = Field(default_factory=list)
    expected_task_owner_category: str = Field(min_length=1)
    scenario_summary: str = Field(min_length=1)


class NormalizedCase(BaseModel):
    case_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    normalized_account_info: dict[str, Any] = Field(default_factory=dict)
    document_refs: list[DocumentRef] = Field(default_factory=list)
    extracted_requirements: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    package_complete: bool = True
    risk_signals: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)


class EvidenceSpan(BaseModel):
    source_document_type: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    normalized_fact: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class Finding(BaseModel):
    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    finding_type: str = Field(min_length=1)
    severity: Severity
    route: Route
    summary: str = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class RoutingDecision(BaseModel):
    case_id: str = Field(min_length=1)
    recommended_route: Route
    confidence: float = Field(ge=0.0, le=1.0)
    approval_required: bool
    reasons: list[str] = Field(default_factory=list)
    triggered_rules: list[str] = Field(default_factory=list)
    secondary_routes: list[Route] = Field(default_factory=list)


class Approval(BaseModel):
    approval_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    status: ApprovalStatus
    reviewer: str | None = None
    comments: str | None = None
    original_route: Route
    final_route: Route | None = None
    requested_info: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None


class GeneratedBrief(BaseModel):
    case_id: str = Field(min_length=1)
    case_summary: str = Field(min_length=1)
    customer_account_summary: str = Field(min_length=1)
    final_route: Route
    risk_summary: str = Field(min_length=1)
    evidence_backed_findings: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    implementation_considerations: list[str] = Field(default_factory=list)
    approval_decision_summary: str = Field(default="")
    recommended_next_steps: list[str] = Field(default_factory=list)


class GeneratedTask(BaseModel):
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    owner_function: str = Field(min_length=1)
    priority: TaskPriority = "medium"
    due_category: str = Field(min_length=1)
    source_finding_ids: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    status: TaskStatus = "open"


class TraceRecord(BaseModel):
    case_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    model_provider_label: str = Field(min_length=1)
    inputs_summary: str
    outputs_summary: str
    latency_ms: int = Field(ge=0)
    token_count: int = Field(ge=0, default=0)
    cost_usd: float = Field(ge=0.0, default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalResult(BaseModel):
    case_id: str = Field(min_length=1)
    expected_route: Route | None = None
    actual_route: Route
    route_pass: bool
    grounding_pass: bool
    approval_pass: bool
    brief_completeness_pass: bool
    notes: str | None = None


class KPIRecord(BaseModel):
    case_id: str = Field(min_length=1)
    final_route: Route
    straight_through: bool
    approval_required: bool
    reviewer_override: bool = False
    processing_time_ms: int | None = None
    generated_task_count: int = Field(ge=0)


class PlaybookRuleMatch(BaseModel):
    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    route: Route
    severity: Severity
    finding_type: str = "policy"
    summary: str = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class CaseStateSnapshot(BaseModel):
    case_id: str
    state: CaseStatus
    intake: IntakePackage
    normalized_case: NormalizedCase | None = None
    routing_decision: RoutingDecision | None = None
    approval: Approval | None = None


class WorkflowResult(BaseModel):
    case_id: str
    state: CaseStatus
    case: IntakePackage | None = None
    normalized_case: NormalizedCase | None = None
    findings: list[Finding] = Field(default_factory=list)
    routing_decision: RoutingDecision | None = None
    approval: Approval | None = None
    brief: GeneratedBrief | None = None
    tasks: list[GeneratedTask] = Field(default_factory=list)
    traces: list[TraceRecord] = Field(default_factory=list)
    eval_result: EvalResult | None = None
    kpi: KPIRecord | None = None
    trace_count: int = 0


class WorkflowCaseQuery(BaseModel):
    route: Route | None = None
    state: CaseStatus | None = None
    search: str | None = None
