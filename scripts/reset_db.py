from __future__ import annotations

from workflows.storage import WorkflowStorage


def main() -> None:
    storage = WorkflowStorage("data/runtime/app.sqlite3")
    storage.clear()
    storage.initialize()
    print("reset complete")


if __name__ == "__main__":
    main()
