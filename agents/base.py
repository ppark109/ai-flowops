from __future__ import annotations

import hashlib
import os
import time
import uuid

from schemas.case import TraceRecord


def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def contains_any(value: str, needles: list[str]) -> bool:
    if not needles:
        return False
    haystack = normalize_text(value)
    return any(normalize_text(needle) in haystack for needle in needles)


def quote_from_text(text: str, needles: list[str]) -> str:
    haystack = normalize_text(text)
    for needle in needles:
        token = normalize_text(needle)
        if token and token in haystack:
            start = haystack.index(token)
            end = start + len(token)
            excerpt_start = text.rfind("\n\n", 0, start)
            excerpt_end = text.find("\n\n", end)
            if excerpt_start == -1:
                excerpt_start = max(0, start - 80)
            else:
                excerpt_start += 2
            if excerpt_end == -1:
                excerpt_end = min(len(text), end + 180)
            excerpt = text[excerpt_start:excerpt_end].strip()
            if len(excerpt) > 420:
                window_start = max(0, start - 120)
                window_end = min(len(text), end + 220)
                excerpt = text[window_start:window_end].strip()
            return excerpt
    return (text or "")[:160].strip()


def evidence_for_rule(evidence: list, rule_id: str, fallback_count: int = 1) -> list:
    aliases = {
        "missing_dpa_general": "missing_dpa_for_regulated_data",
        "termination_terms_risk": "termination_terms",
    }
    evidence_fact = aliases.get(rule_id, rule_id)
    matching = [
        item for item in evidence if getattr(item, "normalized_fact", None) == evidence_fact
    ]
    if matching:
        return matching[:fallback_count]
    return list(evidence[:fallback_count])


def try_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def next_finding_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def build_trace(
    case_id: str,
    step_name: str,
    agent_name: str,
    inputs_summary: str,
    outputs_summary: str,
    start_time: float,
    model_provider_label: str | None = None,
) -> TraceRecord:
    return TraceRecord(
        case_id=case_id,
        step_name=step_name,
        agent_name=agent_name,
        model_provider_label=model_provider_label or "deterministic-fallback",
        inputs_summary=inputs_summary,
        outputs_summary=outputs_summary,
        latency_ms=max(0, int((time.perf_counter() - start_time) * 1000)),
        token_count=0,
        cost_usd=0.0,
    )


def is_api_enabled() -> bool:
    return bool(os.getenv("AI_FLOWOPS_AGENT_MODE_API"))
