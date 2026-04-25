from __future__ import annotations

import re
import time

from agents.base import build_trace
from schemas.case import EvidenceSpan, Finding, IntakePackage, NormalizedCase, TraceRecord


class FinanceReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        payload: IntakePackage,
        normalized_case: NormalizedCase,
        evidence: list[EvidenceSpan],
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        text = " ".join([payload.order_form_text, payload.contract_text]).lower()
        findings: list[Finding] = []

        if "45%" in text or "50%" in text or ("discount" in text and "above" in text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-discount-threshold",
                    "discount above threshold",
                    "medium",
                    "finance",
                    evidence,
                    confidence=0.95,
                )
            )

        if "sla credits" in text or "custom credits" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-sla-credits",
                    "custom SLA credits requested",
                    "medium",
                    "finance",
                    evidence,
                    confidence=0.93,
                )
            )

        if "penalty" in text or re.search(r"penal", text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-unusual-penalty",
                    "unusual penalty terms",
                    "medium",
                    "finance",
                    evidence,
                    confidence=0.9,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="finance_review",
            agent_name="FinanceReviewAgent",
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
        source_agent="FinanceReviewAgent",
    )
