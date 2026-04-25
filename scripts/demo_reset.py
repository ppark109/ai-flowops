from __future__ import annotations

from workflows.orchestrator import WorkflowOrchestrator


def main() -> None:
    orchestrator = WorkflowOrchestrator()
    try:
        orchestrator.store.clear()
        inserted, skipped = orchestrator.seed("data/seed/cases", overwrite=True)
        print(f"seeded inserted={inserted} skipped={skipped}")
        for case in orchestrator.list_cases():
            orchestrator.run_case(case["case_id"])
        print("demo reset complete")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
