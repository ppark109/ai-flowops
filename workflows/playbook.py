from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from agents.evidence import select_evidence_for_rule
from schemas.case import EvidenceSpan, Finding, NormalizedCase
from schemas.playbook import Playbook
from workflows.routing import ROUTES


def load_playbook(path: Path) -> Playbook:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Playbook must be a YAML object: {path}")
    return Playbook.model_validate(raw)


def load_default_playbook() -> Playbook:
    return load_playbook(Path("playbooks/default.yaml"))


def rule_ids_by_route(playbook: Playbook) -> dict[str, list[str]]:
    route_map: dict[str, list[str]] = {}
    for rule in playbook.rules:
        route_map.setdefault(rule.route, []).append(rule.id)
    return route_map


def raw_rule_conditions(playbook: Playbook) -> list[dict[str, Any]]:
    return [rule.when for rule in playbook.rules]


def validate_playbook(playbook: Playbook) -> None:
    ids: set[str] = set()
    for rule in playbook.rules:
        if not rule.id:
            raise ValueError("Rule id must be non-empty.")
        if rule.id in ids:
            raise ValueError(f"Duplicate rule id: {rule.id}")
        ids.add(rule.id)
        if not rule.description:
            raise ValueError(f"Rule {rule.id} missing description.")
        if rule.route not in ROUTES:
            raise ValueError(f"Rule {rule.id} has unsupported route {rule.route}")
        if rule.severity in {"high", "critical"} and not rule.approval_required:
            raise ValueError(f"Rule {rule.id} requires approval for high/critical severity.")

    if len(playbook.rules) < 12 or len(playbook.rules) > 15:
        raise ValueError("Playbook must include 12-15 rules.")

    route_map = rule_ids_by_route(playbook)
    for route in ROUTES:
        if route != "auto_approve" and not route_map.get(route):
            raise ValueError(f"Route {route} has no rules.")
    if not route_map.get("auto_approve"):
        raise ValueError("At least one auto-approve route rule is required.")


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def _collect_searchable(normalized_case: NormalizedCase, evidence: list[EvidenceSpan]) -> str:
    parts = [
        " ".join(e.normalized_fact.lower() for e in evidence),
        " ".join(normalized_case.extracted_requirements).lower(),
        " ".join(s.lower() for s in normalized_case.risk_signals),
        " ".join(
            v.lower()
            for v in normalized_case.normalized_account_info.values()
            if isinstance(v, str)
        ),
    ]
    return " ".join(parts)


def rule_matches(
    rule_when: dict[str, Any], normalized_case: NormalizedCase, evidence: list[EvidenceSpan]
) -> bool:
    if not rule_when:
        return False

    searchable = _collect_searchable(normalized_case, evidence)

    contains_any = rule_when.get("contains_any", [])
    if contains_any and not any(_contains_phrase(searchable, token) for token in contains_any):
        return False

    contains_all = rule_when.get("contains_all", [])
    if contains_all and not all(_contains_phrase(searchable, token) for token in contains_all):
        return False

    missing_fields = set(rule_when.get("missing_fields", []))
    if missing_fields and not missing_fields.intersection(set(normalized_case.missing_info)):
        return False

    required_signals = set(rule_when.get("required_signals", []))
    if required_signals and not required_signals.issubset(set(normalized_case.risk_signals)):
        return False

    requires_metadata = rule_when.get("requires_metadata", {})
    for key, expected in requires_metadata.items():
        if str(normalized_case.metadata.get(key, "")).lower() != str(expected).lower():
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
                summary=f"Playbook rule '{rule.id}' matched: {rule.description}",
                evidence=select_evidence_for_rule(
                    evidence,
                    rule_id=rule.id,
                    keywords=tuple(_rule_keywords(rule.when)),
                    required_evidence=tuple(rule.required_evidence),
                    max_items=2,
                ),
                confidence=0.95,
                source_agent="playbook",
            )
            findings.append(finding)
    return findings


def _rule_keywords(rule_when: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    for key in ("contains_any", "contains_all", "required_signals"):
        for value in rule_when.get(key, []):
            if value not in keywords:
                keywords.append(value)
    return keywords
