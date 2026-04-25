from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from schemas.case import IntakePackage, SeedCase
from workflows.storage import WorkflowStore


def _normalize_case_id(case_id: str) -> str:
    if case_id.startswith("seed-impl-"):
        return case_id.replace("seed-impl-", "seed-implementation-", 1)
    return case_id


def _load_json_file(path: Path) -> SeedCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["case_id"] = _normalize_case_id(raw.get("case_id", ""))
    case = SeedCase.model_validate(raw)
    return case


def load_case_files(folder: Path) -> list[SeedCase]:
    cases = []
    for file in sorted(folder.glob("*.json")):
        cases.append(_load_json_file(file))
    return cases


def seed_cases(
    store: WorkflowStore,
    folder: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[int, int]:
    path = Path(folder)
    cases = load_case_files(path)
    inserted = 0
    skipped = 0
    for case in cases:
        if (not overwrite) and _case_exists(store, case.case_id):
            skipped += 1
            continue
        store.upsert_case(case, status="draft")
        inserted += 1
    return inserted, skipped


def _case_exists(store: WorkflowStore, case_id: str) -> bool:
    try:
        store.get_status(case_id)
        return True
    except KeyError:
        return False


def seed_from_files(
    store: WorkflowStore,
    folder: str | Path,
    on_case: Callable[[IntakePackage], None] | None = None,
) -> dict[str, int]:
    seed = load_case_files(Path(folder))
    inserted = 0
    for item in seed:
        if on_case is not None:
            on_case(item)
        store.upsert_case(item, status="draft")
        inserted += 1
    return {"inserted": inserted, "total": len(seed)}
