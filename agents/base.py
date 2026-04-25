from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from schemas.case import TraceRecord


def build_trace(
    case_id: str,
    step_name: str,
    agent_name: str,
    inputs_summary: str,
    outputs_summary: str,
    start_time: float,
) -> TraceRecord:
    return TraceRecord(
        case_id=case_id,
        step_name=step_name,
        agent_name=agent_name,
        model_provider_label="deterministic-fallback",
        inputs_summary=inputs_summary,
        outputs_summary=outputs_summary,
        latency_ms=max(0, int((time.perf_counter() - start_time) * 1000)),
    )


def next_finding_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def normalize_text(value: str) -> str:
    return (value or "").lower()


def contains_any(value: str, needles: list[str]) -> bool:
    lowered = normalize_text(value)
    return any(normalize_text(needle) in lowered for needle in needles)


def quote_from_text(value: str, needles: list[str]) -> str:
    lowered = normalize_text(value)
    for phrase in needles:
        lower_phrase = normalize_text(phrase)
        if lower_phrase in lowered:
            start = lowered.index(lower_phrase)
            return value[max(0, start - 50) : start + len(phrase) + 50].strip()
    return value[:180]


def phrase_present(value: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if contains_any(value, [phrase]):
            return phrase
    return None


def stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
