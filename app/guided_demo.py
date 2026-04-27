from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CASE_ID = "demo-gov-benefits-001"
CASE_PATH = Path("data/guided_demo/flagship_case.json")
DOCUMENTS_DIR = Path("data/guided_demo/documents")
STEP_ORDER = (
    "received",
    "extraction",
    "recommendation",
    "routing",
    "reviews",
    "synthesis",
    "decision",
)
COMBINED_ROUTE_STEPS = {"recommendation", "routing"}


@lru_cache
def load_case_room_demo() -> dict[str, Any]:
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def get_case_room_context() -> dict[str, Any]:
    demo = load_case_room_demo()
    return {
        "demo": demo,
        "case": demo["case"],
        "departments": demo["departments"],
        "stages": demo["stages"],
    }


def get_walkthrough_context(step: str | None = None) -> dict[str, Any]:
    demo = load_case_room_demo()
    stage_id = step if step in STEP_ORDER else "extraction"
    stage = _stage_by_id(demo, stage_id)
    stage_index = STEP_ORDER.index(stage_id)
    previous_step = STEP_ORDER[stage_index - 1] if stage_index > 0 else None
    next_step = STEP_ORDER[stage_index + 1] if stage_index + 1 < len(STEP_ORDER) else None

    view = "recommendation_routing" if stage_id in COMBINED_ROUTE_STEPS else stage_id
    active_steps = COMBINED_ROUTE_STEPS if stage_id in COMBINED_ROUTE_STEPS else {stage_id}

    return {
        **get_case_room_context(),
        "stage": stage,
        "stage_id": stage_id,
        "active_steps": active_steps,
        "view": view,
        "previous_step": previous_step,
        "next_step": next_step,
    }


def get_department_detail_context(department_id: str | None = None) -> dict[str, Any]:
    demo = load_case_room_demo()
    selected = department_id or "legal"
    department = next(
        (item for item in demo["departments"] if item["id"] == selected),
        demo["departments"][0],
    )
    evidence = [
        item
        for item in demo["evidence_items"]
        if _department_slug(item["department"]) == department["id"]
    ]
    return {
        **get_case_room_context(),
        "department": department,
        "department_evidence": evidence,
    }


def get_evidence_map_context(
    department: str | None = None, risks_only: bool = False
) -> dict[str, Any]:
    demo = load_case_room_demo()
    evidence = demo["evidence_items"]
    if department:
        evidence = [item for item in evidence if _department_slug(item["department"]) == department]
    if risks_only:
        evidence = [item for item in evidence if item["risk"]]
    return {
        **get_case_room_context(),
        "evidence_items": evidence,
        "selected_department": department or "all",
        "risks_only": risks_only,
    }


def get_source_document_context(active: str | None = None) -> dict[str, Any]:
    demo = load_case_room_demo()
    active_id = active or "ev-liability-cap"
    active_item = next(
        (item for item in demo["evidence_items"] if item["id"] == active_id),
        demo["evidence_items"][0],
    )
    return {
        **get_case_room_context(),
        "active_item": active_item,
        "evidence_items": demo["evidence_items"],
    }


def get_kpi_context() -> dict[str, Any]:
    demo = load_case_room_demo()
    stage_times = demo["kpi_dashboard"]["stage_times"]
    max_stage_seconds = max(item["seconds"] for item in stage_times)
    audit_density = _audit_density_with_events(demo)
    max_audit_count = max(item["count"] for item in audit_density)
    return {
        **get_case_room_context(),
        "kpi_dashboard": {**demo["kpi_dashboard"], "audit_density": audit_density},
        "max_stage_seconds": max_stage_seconds,
        "max_audit_count": max_audit_count,
    }


def get_document_package_context() -> dict[str, Any]:
    return get_case_room_context()


def get_document_context(document_id: str) -> dict[str, Any]:
    demo = load_case_room_demo()
    document = next(
        (item for item in demo["source_documents"] if item["id"] == document_id),
        None,
    )
    if document is None:
        raise KeyError(document_id)
    path = DOCUMENTS_DIR / document["filename"]
    return {
        **get_case_room_context(),
        "document": document,
        "document_body": path.read_text(encoding="utf-8"),
    }


def resolve_evidence_references() -> bool:
    demo = load_case_room_demo()
    for item in demo["evidence_items"]:
        document = next(
            doc for doc in demo["source_documents"] if doc["id"] == item["document_id"]
        )
        path = DOCUMENTS_DIR / document["filename"]
        document_text = _normalize_reference_text(path.read_text(encoding="utf-8"))
        full_source = _normalize_reference_text(item["full_source"])
        phrase = _normalize_reference_text(item["source_phrase"].replace("...", " "))
        phrase_words = [word for word in phrase.split() if len(word) > 3]
        if full_source not in document_text:
            return False
        if phrase_words and not all(word in document_text for word in phrase_words[:6]):
            return False
    return True


def _normalize_reference_text(value: str) -> str:
    return (
        " ".join(value.lower().split())
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("â€™", "'")
        .replace("â€œ", '"')
        .replace("â€\u009d", '"')
    )


def _stage_by_id(demo: dict[str, Any], stage_id: str) -> dict[str, Any]:
    for stage in demo["stages"]:
        if stage["id"] == stage_id:
            return stage
    raise KeyError(stage_id)


def _department_slug(department: str) -> str:
    return department.lower().replace("/", "-").replace(" ", "-")


def _audit_density_with_events(demo: dict[str, Any]) -> list[dict[str, Any]]:
    events = demo["audit_events"]
    density = []
    for item in demo["kpi_dashboard"]["audit_density"]:
        bucket_events = [
            event for event in events if str(event["time"]).startswith(str(item["time"]))
        ]
        density.append({**item, "events": bucket_events})
    return density
