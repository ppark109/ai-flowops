from __future__ import annotations

import time

from agents.base import build_trace
from schemas.case import EvidenceSpan, Finding, IntakePackage, NormalizedCase, TraceRecord


class SecurityReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        payload: IntakePackage,
        normalized_case: NormalizedCase,
        evidence: list[EvidenceSpan],
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        text = " ".join([payload.security_questionnaire_text, payload.contract_text]).lower()
        findings: list[Finding] = []

        if "dpa" in text and ("missing" in text or "not provided" in text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-missing-dpa",
                    "missing DPA for security-sensitive intake",
                    "high",
                    "security",
                    evidence,
                    confidence=0.96,
                )
            )

        if "data residency" in text or "residency request" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-data-residency",
                    "data residency request identified",
                    "medium",
                    "security",
                    evidence,
                    confidence=0.95,
                )
            )

        if "regulated" in text or "sensitive" in text or "pii" in text or "phi" in text:
            if (
                not any(f.finding_id.endswith("playbook-missing-dpa") for f in findings)
                and "dpa" not in text
            ):
                findings.append(
                    _finding(
                        payload.case_id,
                        "playbook-regulated-no-artifact",
                        "regulated data without explicit security artifact",
                        "high",
                        "security",
                        evidence,
                        confidence=0.9,
                    )
                )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="security_review",
            agent_name="SecurityReviewAgent",
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
) -> Finding:
    return Finding(
        finding_id=f"{case_id}-{rule_id}",
        rule_id=rule_id,
        finding_type="specialist",
        severity=severity,
        route=route,
        summary=summary,
        evidence=evidence[:2],
        confidence=confidence,
        source_agent="SecurityReviewAgent",
    )
