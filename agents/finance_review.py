from __future__ import annotations

import re
import time

from agents.base import build_trace, evidence_for_rule, next_finding_id
from schemas.case import Finding, IntakePackage, NormalizedCase, TraceRecord


class FinanceReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase, evidence: list
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        findings: list[Finding] = []
        text = (
            f"{payload.order_form_text} {payload.contract_text} {payload.intake_email_text}".lower()
        )
        discount = _discount_percent(text)

        if discount and discount > 35:
            findings.append(
                _finding(
                    payload.case_id,
                    "discount_above_threshold",
                    "finance",
                    "medium",
                    f"Discount is {int(discount)}%, above policy threshold.",
                    evidence,
                )
            )

        if "sla credit" in text or "service credit" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "custom_sla_credits",
                    "finance",
                    "medium",
                    "Customer asks for custom SLA credit terms.",
                    evidence,
                )
            )

        if "fixed fee" in text and ("mainframe" in text or "integration" in text):
            findings.append(
                _finding(
                    payload.case_id,
                    "fixed_fee_scope_risk",
                    "finance",
                    "medium",
                    "Fixed-fee scope includes integration and stabilization risk.",
                    evidence,
                )
            )

        if "penalty" in text or "refund" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "unusual_penalty_terms",
                    "finance",
                    "high",
                    "Penalty/refund terms require finance review.",
                    evidence,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="finance_review",
            agent_name="FinanceReviewAgent",
            inputs_summary=f"risk_signals={len(normalized_case.risk_signals)}",
            outputs_summary=f"findings={len(findings)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return findings, trace


def _discount_percent(text: str) -> float | None:
    match = re.search(r"(\d{2,3})\s*%", text.lower())
    if not match:
        return None
    return float(match.group(1))


def _finding(
    case_id: str, rule_id: str, route: str, severity: str, summary: str, evidence: list
) -> Finding:
    from schemas.case import EvidenceSpan

    source_evidence = evidence_for_rule(evidence, rule_id)
    if not source_evidence:
        source_evidence = [
            EvidenceSpan(
                source_document_type="order_form",
                locator="order_form:0",
                quote="finance scope text",
                normalized_fact=rule_id,
                confidence=0.6,
            )
        ]
    return Finding(
        finding_id=next_finding_id("finance"),
        rule_id=rule_id,
        finding_type="finance_review",
        severity=severity,  # type: ignore[arg-type]
        route=route,  # type: ignore[arg-type]
        summary=summary,
        evidence=source_evidence,
        confidence=0.9,
    )
