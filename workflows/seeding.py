from __future__ import annotations

import json
from pathlib import Path

from schemas.case import SeedCase
from workflows.storage import WorkflowStorage


def load_seed_cases(folder: str = "data/seed/cases") -> list[SeedCase]:
    cases: list[SeedCase] = []
    for path in sorted(Path(folder).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(SeedCase.model_validate(payload))
    return cases


def load_held_out_cases(folder: str = "data/held_out/cases") -> list[SeedCase]:
    cases: list[SeedCase] = []
    for path in sorted(Path(folder).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(SeedCase.model_validate(payload))
    return cases


def seed_database(
    storage: WorkflowStorage, folder: str = "data/seed/cases", wipe: bool = False
) -> list[SeedCase]:
    if wipe:
        storage.clear()
    seeded = load_seed_cases(folder)
    for case in seeded:
        storage.upsert_case(case, state="draft")
    return seeded
