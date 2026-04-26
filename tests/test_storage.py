from pathlib import Path

from schemas.case import EvalResult, KPIRecord
from workflows.orchestrator import WorkflowOrchestrator


def test_seed_and_query_roundtrip(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "store.sqlite3")
    try:
        inserted, skipped = orchestrator.seed("data/seed/cases", overwrite=True)
        assert inserted == 24
        assert skipped == 0

        all_cases = orchestrator.list_cases()
        assert len(all_cases) == 24

        first = all_cases[0]
        case_id = first["case_id"]
        state = orchestrator.store.get_case_state(case_id)
        assert state.case_id == case_id
        assert state.state == "draft"
    finally:
        orchestrator.close()


def test_kpi_summary_counts_cases_not_only_kpi_rows(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "kpis.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        initial = orchestrator.store.get_kpi_summary()
        assert initial["total_cases"] == 24
        assert initial["straight_through_count"] == 0
        assert initial["escalation_count"] == 0

        orchestrator.store.set_status("seed-clean-001", "completed")
        orchestrator.store.save_kpi(
            KPIRecord(
                case_id="seed-clean-001",
                final_route="auto_approve",
                straight_through=True,
                approval_required=False,
                reviewer_override=False,
                generated_task_count=1,
            )
        )
        updated = orchestrator.store.get_kpi_summary()
        assert updated["total_cases"] == 24
        assert updated["straight_through_count"] == 1
        assert updated["avg_tasks"] == 1.0
    finally:
        orchestrator.close()


def test_case_list_reports_actual_route_separately_from_expected_route(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "routes.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        before = {
            row["case_id"]: row
            for row in orchestrator.list_cases()
            if row["case_id"] == "seed-legal-001"
        }["seed-legal-001"]
        assert before["actual_route"] is None
        assert before["expected_route"] == "legal"

        orchestrator.run_case("seed-legal-001")
        after = {
            row["case_id"]: row
            for row in orchestrator.list_cases()
            if row["case_id"] == "seed-legal-001"
        }["seed-legal-001"]
        assert after["actual_route"] == "legal"
        assert after["expected_route"] == "legal"
    finally:
        orchestrator.close()


def test_eval_summary_total_rate_uses_real_outcomes(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "eval-summary.sqlite3")
    try:
        orchestrator.seed("data/seed/cases", overwrite=True)
        orchestrator.store.save_eval_result(
            "run-1",
            EvalResult(
                case_id="seed-clean-001",
                expected_route="auto_approve",
                actual_route="auto_approve",
                route_pass=True,
                approval_pass=True,
                grounding_pass=True,
                brief_completeness_pass=True,
            ),
        )
        orchestrator.store.save_eval_result(
            "run-1",
            EvalResult(
                case_id="seed-legal-001",
                expected_route="legal",
                actual_route="security",
                route_pass=False,
                approval_pass=True,
                grounding_pass=True,
                brief_completeness_pass=True,
            ),
        )

        summary = orchestrator.store.get_eval_summary("run-1")
        assert summary["total_rate"] == 0.5
        assert summary["route_rate"] == 0.5
        assert summary["approval_rate"] == 1.0
    finally:
        orchestrator.close()
