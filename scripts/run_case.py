from __future__ import annotations

import argparse

from workflows.orchestrator import WorkflowOrchestrator
from workflows.playbook import load_default_playbook
from workflows.storage import WorkflowStorage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--db", default="data/runtime/app.sqlite3")
    args = parser.parse_args()

    storage = WorkflowStorage(args.db)
    orchestrator = WorkflowOrchestrator(storage, load_default_playbook())
    result = orchestrator.run_case_by_id(args.case_id)
    print(result.state)


if __name__ == "__main__":
    main()
