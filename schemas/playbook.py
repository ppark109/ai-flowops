from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.case import Route, Severity

ApprovalPolicy = Literal["always", "on_high_risk", "on_low_confidence", "never"]


class PlaybookRule(BaseModel):
    id: str
    description: str
    when: dict[str, Any]
    severity: Severity
    route: Route
    approval_required: bool
    required_evidence: list[str] = Field(default_factory=list)
    task_template: str | None = None


class Playbook(BaseModel):
    name: str
    version: str
    approval_policy: ApprovalPolicy = "on_high_risk"
    rules: list[PlaybookRule]


class PlaybookValidationError(ValueError):
    """Raised when the playbook violates local deterministic-policy constraints."""
