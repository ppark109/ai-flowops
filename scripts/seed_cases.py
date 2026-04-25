from __future__ import annotations

from pathlib import Path

from workflows.orchestrator import WorkflowOrchestrator
from workflows.seeding import seed_cases


def main() -> None:
    orchestrator = WorkflowOrchestrator()
    try:
        inserted, skipped = seed_cases(orchestrator.store, Path("data/seed/cases"), overwrite=True)
        print(f"seeded inserted={inserted} skipped={skipped}")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
