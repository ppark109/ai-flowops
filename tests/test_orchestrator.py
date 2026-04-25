from pathlib import Path

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
    finally:
        orchestrator.close()
