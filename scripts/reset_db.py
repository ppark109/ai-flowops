from __future__ import annotations

from workflows.storage import WorkflowStore


def main() -> None:
    store = WorkflowStore()
    try:
        store.clear()
        print("runtime db cleared")
    finally:
        store.close()


if __name__ == "__main__":
    main()
