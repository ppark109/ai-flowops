from __future__ import annotations

import sys

from workflows.orchestrator import WorkflowOrchestrator


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/run_case.py <case_id>")
    case_id = sys.argv[1]
    orchestrator = WorkflowOrchestrator()
    try:
        result = orchestrator.run_case(case_id)
        print(result.model_dump_json(indent=2))
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
