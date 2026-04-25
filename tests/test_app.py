from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from workflows.orchestrator import WorkflowOrchestrator
from workflows.routing import ROUTES
from workflows.seeding import seed_cases


def test_healthz_reports_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta_expected_routes() -> None:
    response = TestClient(create_app()).get("/meta")
    assert response.status_code == 200
    assert response.json()["routes"] == list(ROUTES)


def test_api_can_seed_and_run_case(tmp_path: Path) -> None:
    # Use a temporary DB for a deterministic run in tests.
    app = create_app()
    app.state.orchestrator.close()
    app.state.orchestrator = WorkflowOrchestrator(db_path=tmp_path / "app.sqlite3")

    client = TestClient(app)
    seeded = client.post("/api/cases/seed").json()
    assert "inserted" in seeded

    case_id = sorted(Path("data/seed/cases").glob("*.json"))[0].stem
    response = client.post(f"/api/cases/{case_id}/run")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert "routing" in data


def test_api_approval_flow(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "approval.sqlite3")
    try:
        inserted, skipped = seed_cases(orchestrator.store, "data/seed/cases", overwrite=True)
        case_id = "seed-legal-001"
        result = orchestrator.run_case(case_id)
        assert result.approval_id
        state = orchestrator.store.get_case_state(case_id)
        assert state.approval and state.approval.status == "pending"

        app = create_app()
        app.state.orchestrator.close()
        app.state.orchestrator = orchestrator
        client = TestClient(app)

        approval_id = result.approval_id
        response = client.post(
            f"/api/approvals/{approval_id}/approve", json={"reviewer": "qa", "comments": "ok"}
        )
        assert response.status_code == 200
        state = orchestrator.store.get_case_state(case_id)
        assert state.approval is not None
        assert state.approval.status == "approved"
    finally:
        orchestrator.close()
