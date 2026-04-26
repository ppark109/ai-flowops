from __future__ import annotations

import re
import time

from agents.base import build_trace
from agents.evidence import select_evidence_for_rule
from schemas.case import EvidenceSpan, Finding, IntakePackage, NormalizedCase, TraceRecord


class ImplementationReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        payload: IntakePackage,
        normalized_case: NormalizedCase,
        evidence: list[EvidenceSpan],
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        text = " ".join([payload.implementation_notes, payload.intake_email_text]).lower()
        findings: list[Finding] = []

        if re.search(r"next week|asap|urgent|rush", text) or "aggressive go-live" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-aggressive-go-live",
                    "aggressive go-live date",
                    "medium",
                    "implementation",
                    evidence,
                    confidence=0.95,
                    keywords=("aggressive", "next week", "asap", "urgent", "rush"),
                    required_evidence=("notes_span", "intake_span"),
                )
            )

        if "custom sap plugin" in text or "unsupported integration" in text or "legacy" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-unsupported-integration",
                    "unsupported integration requested",
                    "medium",
                    "implementation",
                    evidence,
                    confidence=0.93,
                    keywords=("custom sap plugin", "unsupported integration", "legacy"),
                    required_evidence=("notes_span",),
                )
            )

        if "unclear owner" in text or "no owner" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-unclear-owner",
                    "unclear customer owner",
                    "medium",
                    "implementation",
                    evidence,
                    confidence=0.9,
                    keywords=("unclear owner", "no owner", "owner to be determined"),
                    required_evidence=("notes_span",),
                )
            )

        if "statement of work" in text and "missing" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-missing-sow",
                    "missing SOW reference",
                    "medium",
                    "implementation",
                    evidence,
                    confidence=0.9,
                    keywords=("statement of work", "missing sow"),
                    required_evidence=("notes_span",),
                )
            )

        if not normalized_case.package_complete:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-incomplete-package",
                    "incomplete intake package",
                    "medium",
                    "implementation",
                    evidence,
                    confidence=0.94,
                    keywords=("incomplete", "missing"),
                    required_evidence=("intake_span",),
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="implementation_review",
            agent_name="ImplementationReviewAgent",
            inputs_summary=f"risk_signals={len(normalized_case.risk_signals)}",
            outputs_summary=f"findings={len(findings)}",
            start_time=start,
        )
        return findings, trace


def _finding(
    case_id: str,
    rule_id: str,
    summary: str,
    severity: str,
    route: str,
    evidence: list[EvidenceSpan],
    *,
    confidence: float,
    keywords: tuple[str, ...],
    required_evidence: tuple[str, ...],
) -> Finding:
    return Finding(
        finding_id=f"{case_id}-{rule_id}",
        rule_id=rule_id,
        finding_type="specialist",
        severity=severity,
        route=route,
        summary=summary,
        evidence=select_evidence_for_rule(
            evidence,
            rule_id=rule_id,
            keywords=keywords,
            required_evidence=required_evidence,
        ),
        confidence=confidence,
        source_agent="ImplementationReviewAgent",
    )
