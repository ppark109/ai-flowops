from pathlib import Path

import pytest

from workflows.orchestrator import WorkflowOrchestrator
from workflows.seeding import load_case_files


def test_all_seed_cases_run_end_to_end(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "flow.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        cases = load_case_files(Path("data/seed/cases"))
        for item in cases:
            result = orchestrator.run_case(item.case_id)
            if result.routing.approval_required:
                assert result.approval_id
                assert result.has_brief is False
                assert result.task_count == 0
            else:
                assert result.has_brief is True
                assert result.task_count == 1
    finally:
        orchestrator.close()


def test_approval_actions_are_reflected(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "flow2.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        case_id = "seed-legal-001"
        result = orchestrator.run_case(case_id)
        assert result.approval_id is not None

        state = orchestrator.store.get_case_state(case_id)
        assert state.approval is not None

        resumed = orchestrator.apply_approval(
            result.approval_id,
            "approve",
            reviewer="qa",
            comments="approved after review",
        )
        assert resumed.approval is not None
        assert resumed.approval.status == "approved"
        with pytest.raises(ValueError, match="terminal state"):
            orchestrator.run_case(case_id)

        # request route override
        case_id = "seed-implementation-001"
        result2 = orchestrator.run_case(case_id)
        assert result2.approval_id
        resumed2 = orchestrator.apply_approval(
            result2.approval_id,
            "override_route",
            reviewer="lead",
            comments="move to security per architecture review",
            override_route="security",
        )
        assert resumed2.approval is not None
        assert resumed2.approval.final_route == "security"
        with pytest.raises(ValueError, match="cannot be acted on again"):
            orchestrator.apply_approval(
                result2.approval_id,
                "reject",
                reviewer="lead",
                comments="second action should fail",
            )
    finally:
        orchestrator.close()


def test_rejected_approval_cannot_be_reopened_by_second_action(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "closed.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        result = orchestrator.run_case("seed-legal-001")
        assert result.approval_id
        rejected = orchestrator.apply_approval(
            result.approval_id,
            "reject",
            reviewer="qa",
            comments="reject for test",
        )
        assert rejected.approval is not None
        assert rejected.approval.status == "rejected"

        with pytest.raises(ValueError, match="cannot be acted on again"):
            orchestrator.apply_approval(
                result.approval_id,
                "approve",
                reviewer="qa",
                comments="second action should fail",
            )
    finally:
        orchestrator.close()


def test_request_info_stays_in_active_approval_queue(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "request-info.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        result = orchestrator.run_case("seed-legal-001")
        assert result.approval_id
        state = orchestrator.apply_approval(
            result.approval_id,
            "request_info",
            reviewer="qa",
            request_info="Need updated DPA.",
        )
        assert state.approval is not None
        assert state.approval.status == "request_info"

        active_ids = {approval.approval_id for approval in orchestrator.list_approvals()}
        assert result.approval_id in active_ids
    finally:
        orchestrator.close()


def test_findings_use_rule_specific_evidence(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "evidence.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        orchestrator.run_case("seed-legal-001")
        state = orchestrator.store.get_case_state("seed-legal-001")

        liability_findings = [
            finding
            for finding in state.findings
            if finding.rule_id in {"playbook-liability-cap", "liability_cap_above_standard"}
        ]
        assert liability_findings
        for finding in liability_findings:
            assert finding.evidence
            assert all(span.source_document_type == "contract" for span in finding.evidence)
            assert any("liability" in span.normalized_fact for span in finding.evidence)
    finally:
        orchestrator.close()
