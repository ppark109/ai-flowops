from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> None:
    _ensure_project_root()
    from evals.runner import run_eval
    from workflows.orchestrator import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator()
    try:
        result = run_eval(
            orchestrator.store,
            folder=Path("data/held_out/cases"),
            output=Path("evals/baselines/latest.json"),
        )
        print(f"run_id={result['run_id']} route_accuracy={result['route_accuracy']:.2f}")
        print(f"approval_accuracy={result['approval_accuracy']:.2f}")
        print(f"grounding_accuracy={result['grounding_accuracy']:.2f}")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
