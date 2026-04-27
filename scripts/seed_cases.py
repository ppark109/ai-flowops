from __future__ import annotations

import argparse

from workflows.seeding import seed_database
from workflows.storage import WorkflowStorage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wipe", action="store_true")
    parser.add_argument("--db", default="data/runtime/app.sqlite3")
    args = parser.parse_args()

    storage = WorkflowStorage(args.db)
    count = len(seed_database(storage, folder="data/seed/cases", wipe=not args.no_wipe))
    print(f"seeded={count}")


if __name__ == "__main__":
    main()
