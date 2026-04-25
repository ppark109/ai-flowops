from __future__ import annotations

import re
import time

from agents.base import build_trace
from schemas.case import EvidenceSpan, Finding, IntakePackage, NormalizedCase, TraceRecord


class ContractRiskAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        payload: IntakePackage,
        normalized_case: NormalizedCase,
        evidence: list[EvidenceSpan],
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        findings: list[Finding] = []
        text = " ".join([payload.contract_text, payload.order_form_text]).lower()

        if re.search(r"liability\s+cap.*(above|greater|1x|2x|3x)", text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-liability-cap",
                    "liability cap exceeds standard",
                    "high",
                    "legal",
                    evidence,
                )
            )

        if re.search(r"nonstandard\s+indemnity|broader\s+indemnity|unusual\s+indemnity", text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-nonstandard-indemnity",
                    "nonstandard indemnity clause",
                    "high",
                    "legal",
                    evidence,
                )
            )

        if re.search(r"unusually\s+high\s+penalty|unusual\s+penalty|penalty\s+terms", text):
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-unusual-penalty-terms",
                    "unusual penalty terms",
                    "medium",
                    "finance",
                    evidence,
                )
            )

        if "conflicting" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "playbook-conflicting-terms",
                    "conflicting terms across documents",
                    "medium",
                    "implementation",
                    evidence,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="contract_risk_review",
            agent_name="ContractRiskAgent",
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
) -> Finding:
    return Finding(
        finding_id=f"{case_id}-{rule_id}",
        rule_id=rule_id,
        finding_type="specialist",
        severity=severity,
        route=route,
        summary=summary,
        evidence=evidence[:2],
        confidence=0.92,
        source_agent="ContractRiskAgent",
    )
