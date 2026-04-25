import json
from pathlib import Path

from evals.runner import run_eval
from workflows.orchestrator import WorkflowOrchestrator


def test_eval_runner_produces_results(tmp_path: Path) -> None:
    orchestrator = WorkflowOrchestrator(db_path=tmp_path / "eval.sqlite3")
    try:
        out = tmp_path / "latest.json"
        result = run_eval(orchestrator.store, Path("data/held_out/cases"), output=out)
        assert result["total"] == 5
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "rows" in payload
    finally:
        orchestrator.close()
