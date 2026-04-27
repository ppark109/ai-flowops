from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflows.seeding import seed_database
from workflows.storage import WorkflowStorage


def main() -> None:
    storage = WorkflowStorage("data/runtime/app.sqlite3")
    seeded = seed_database(storage, folder="data/seed/cases", wipe=True)
    print(f"reset complete; seeded={len(seeded)}")


if __name__ == "__main__":
    main()
