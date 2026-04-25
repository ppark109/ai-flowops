from pathlib import Path

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
