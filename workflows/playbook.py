from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from agents.base import evidence_for_rule
from schemas.case import EvidenceSpan, Finding, NormalizedCase, Route
from schemas.playbook import Playbook, PlaybookValidationError
from workflows.routing import ROUTES


def load_playbook(path: Path) -> Playbook:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Playbook must be a YAML object: {path}")
    return Playbook.model_validate(raw)


def load_default_playbook() -> Playbook:
    return load_playbook(Path("playbooks/default.yaml"))


def validate_playbook(playbook: Playbook) -> None:
    if not playbook.rules:
        raise PlaybookValidationError("Playbook has no rules.")

    if not 12 <= len(playbook.rules) <= 20:
        raise PlaybookValidationError("Playbook must include 12-20 rules.")

    ids: set[str] = set()
    for rule in playbook.rules:
        if not rule.id:
            raise PlaybookValidationError("Rule id is required.")
        if rule.id in ids:
            raise PlaybookValidationError(f"Duplicate rule id: {rule.id}")
        ids.add(rule.id)
        if not rule.description:
            raise PlaybookValidationError(f"Rule '{rule.id}' missing description.")
        if rule.route not in ROUTES:
            raise PlaybookValidationError(f"Rule '{rule.id}' has unsupported route '{rule.route}'.")
        if rule.severity in {"high", "critical"} and not rule.approval_required:
            raise PlaybookValidationError(
                f"Rule '{rule.id}' has high/critical severity but approval_required=false."
            )

    by_route = rule_ids_by_route(playbook)
    for route in ROUTES:
        if route == "auto_approve":
            continue
        if not by_route.get(route):
            raise PlaybookValidationError(f"Route '{route}' has no configured rules.")
    if not by_route.get("auto_approve"):
        raise PlaybookValidationError("Playbook must define at least one auto-approve rule.")


def rule_ids_by_route(playbook: Playbook) -> dict[Route, list[str]]:
    route_map: dict[Route, list[str]] = {route: [] for route in ROUTES}
    for rule in playbook.rules:
        route_map[rule.route].append(rule.id)
    return route_map


def raw_rule_conditions(playbook: Playbook) -> list[dict[str, Any]]:
    return [rule.when for rule in playbook.rules]


def _contains_any(searchable: str, values: list[str]) -> bool:
    lowered = searchable.lower()
    return any(str(value).lower() in lowered for value in values)


def _contains_all(searchable: str, values: list[str]) -> bool:
    lowered = searchable.lower()
    return all(str(value).lower() in lowered for value in values)


def _collect_searchable_text(normalized_case: NormalizedCase, evidence: list[EvidenceSpan]) -> str:
    normalized_bits = []
    normalized_bits.extend(normalized_case.extracted_requirements)
    normalized_bits.extend(normalized_case.risk_signals)
    normalized_bits.extend(normalized_case.missing_info)
    normalized_bits.extend(e.normalized_fact for e in evidence)
    normalized_bits.extend(normalized_case.normalized_account_info.values())
    return " ".join(str(part).lower() for part in normalized_bits)


def rule_matches(
    rule_when: dict[str, Any], normalized_case: NormalizedCase, evidence: list[EvidenceSpan]
) -> bool:
    if not rule_when:
        return False

    searchable = _collect_searchable_text(normalized_case, evidence)

    contains_any = rule_when.get("contains_any", [])
    if contains_any and not _contains_any(searchable, contains_any):
        return False

    contains_all = rule_when.get("contains_all", [])
    if contains_all and not _contains_all(searchable, contains_all):
        return False

    if "missing_fields" in rule_when:
        missing_fields = set(rule_when.get("missing_fields", []))
        current_missing = set(normalized_case.missing_info)
        if missing_fields:
            if not current_missing.intersection(missing_fields):
                return False
        elif current_missing:
            return False

    if "required_signals" in rule_when:
        required_signals = set(rule_when.get("required_signals", []))
        current_signals = set(normalized_case.risk_signals)
        if required_signals:
            if not required_signals.issubset(current_signals):
                return False
        elif current_signals:
            return False

    for key, expected in (rule_when.get("metadata", {}) or {}).items():
        if str(normalized_case.metadata.get(key, "")).lower() != str(expected).lower():
            return False

    package_complete = rule_when.get("package_complete")
    if package_complete is not None and bool(normalized_case.package_complete) is not bool(
        package_complete
    ):
        return False

    return True


def match_rules(
    playbook: Playbook, normalized_case: NormalizedCase, evidence: list[EvidenceSpan]
) -> list[Finding]:
    findings: list[Finding] = []
    for rule in playbook.rules:
        if rule_matches(rule.when, normalized_case, evidence):
            finding = Finding(
                finding_id=f"playbook-{uuid4().hex[:8]}",
                rule_id=rule.id,
                finding_type="policy",
                severity=rule.severity,
                route=rule.route,
                summary=f"{rule.id}: {rule.description}",
                evidence=evidence_for_rule(evidence, rule.id),
                confidence=0.98,
            )
            findings.append(finding)
    return findings
