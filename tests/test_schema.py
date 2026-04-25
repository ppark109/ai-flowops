import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from schemas.case import (
    Approval,
    EvalResult,
    IntakePackage,
    KPIRecord,
)


def test_valid_seed_payload_loads(tmp_path: Path) -> None:
    case_path = Path("data/seed/cases/seed-clean-001.json")
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    package = IntakePackage.model_validate(payload)
    assert package.case_id == "seed-clean-001"


def test_invalid_route_rejected() -> None:
    with pytest.raises(ValueError):
        IntakePackage(
            case_id="x",
            customer_name="a",
            intake_email_text="...",
            contract_text="...",
            order_form_text="...",
            implementation_notes="...",
            security_questionnaire_text="...",
            submitted_at=datetime.now(UTC),
            expected_route="not-a-route",  # type: ignore[arg-type]
            expected_approval_required=False,
        )


def test_approval_status_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        Approval(
            approval_id="apr-1",
            case_id="c1",
            status="bad",  # type: ignore[arg-type]
            original_route="auto_approve",
            final_route=None,
            reviewer=None,
            comments=None,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )


def test_eval_and_kpi_validate_minimum_fields() -> None:
    eval_record = EvalResult(
        case_id="seed-clean-001",
        expected_route="auto_approve",
        actual_route="auto_approve",
        route_pass=True,
        grounding_pass=True,
        approval_pass=True,
        brief_completeness_pass=True,
    )
    assert eval_record.case_id == "seed-clean-001"

    kpi = KPIRecord(
        case_id="seed-clean-001",
        final_route="auto_approve",
        straight_through=True,
        approval_required=False,
        reviewer_override=False,
        processing_time_ms=None,
        generated_task_count=1,
    )
    assert kpi.generated_task_count == 1
